"""
bubblegum/core/recorder/js.py
=============================
The in-page recorder script (A1).

Injected once per document via ``context.add_init_script``. It installs
capture-phase listeners that, for each meaningful user interaction, distil the
target element into a small JSON payload (action / role / accessible name /
value / fallback selector) and stream it to Python through the
``__bubblegum_record__`` binding exposed by :class:`ActionRecorder`.

Capture rules (kept intentionally small for the MVP):
  - ``input`` drives text-field capture so it does not depend on blur/``change``
    timing (which Playwright's ``fill`` does not reliably emit): text input /
    textarea → ``type`` with the field value. Repeated ``input`` events on one
    field are collapsed downstream so only the final value survives.
  - ``change`` drives the commit-style controls:
      • checkbox / radio  → ``check`` or ``uncheck`` (by checked state)
      • ``<select>``      → ``select`` with the chosen option's visible text
  - ``click`` captures buttons, links and submit/button inputs. Form controls
    handled above are excluded here so they are not double-recorded.

Accessible-name derivation mirrors what the grounding engine keys on: explicit
aria-label / aria-labelledby first, then an associated <label>, then
placeholder, then submit-button value, then trimmed text content, then title.
"""

from __future__ import annotations

# NOTE: plain JS string — no Python .format()/% templating, so literal braces
# are safe. Wrapped as a self-executing IIFE because ``add_init_script`` runs
# the script text as-is (it does not *call* a passed function the way
# ``page.evaluate`` does). Idempotent: re-running on the same document is a
# no-op.
RECORDER_JS = r"""
(() => {
  if (window.__bubblegumRecorderInstalled) return;
  window.__bubblegumRecorderInstalled = true;

  function clean(s) {
    return (s || "").replace(/\s+/g, " ").trim();
  }

  function accessibleName(el) {
    if (!el || !el.getAttribute) return "";
    var aria = el.getAttribute("aria-label");
    if (clean(aria)) return clean(aria);

    var lb = el.getAttribute("aria-labelledby");
    if (lb) {
      var parts = lb.split(/\s+/).map(function (id) {
        var e = document.getElementById(id);
        return e ? clean(e.textContent) : "";
      }).filter(Boolean);
      if (parts.length) return clean(parts.join(" "));
    }

    if (el.id) {
      try {
        var lab = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]');
        if (lab && clean(lab.textContent)) return clean(lab.textContent);
      } catch (e) {}
    }
    if (el.closest) {
      var wrap = el.closest("label");
      if (wrap && clean(wrap.textContent)) return clean(wrap.textContent);
    }

    var ph = el.getAttribute("placeholder");
    if (clean(ph)) return clean(ph);

    var tag = (el.tagName || "").toLowerCase();
    var type = (el.getAttribute("type") || "").toLowerCase();
    if (tag === "input" && (type === "submit" || type === "button") && clean(el.value)) {
      return clean(el.value);
    }

    if (clean(el.textContent)) return clean(el.textContent);

    var title = el.getAttribute("title");
    if (clean(title)) return clean(title);
    return "";
  }

  function roleOf(el) {
    var explicit = el.getAttribute && el.getAttribute("role");
    if (clean(explicit)) return clean(explicit).toLowerCase();
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      var t = (el.getAttribute("type") || "text").toLowerCase();
      if (t === "checkbox") return "checkbox";
      if (t === "radio") return "radio";
      if (t === "submit" || t === "button" || t === "reset" || t === "image") return "button";
      return "textbox";
    }
    return tag;
  }

  function refOf(el, role, name) {
    if (el.id) return "#" + el.id;
    var nm = el.getAttribute && el.getAttribute("name");
    if (clean(nm)) return '[name="' + clean(nm) + '"]';
    if (role && name) return "role=" + role + '[name="' + name + '"]';
    if (role) return "role=" + role;
    return null;
  }

  function send(action, el, extra) {
    var role = roleOf(el);
    var name = accessibleName(el);
    var payload = {
      action: action,
      role: role,
      name: name,
      tag: (el.tagName || "").toLowerCase(),
      fallback_ref: refOf(el, role, name),
    };
    if (extra) {
      for (var k in extra) { if (extra.hasOwnProperty(k)) payload[k] = extra[k]; }
    }
    try { window.__bubblegum_record__(payload); } catch (e) {}
  }

  document.addEventListener("click", function (ev) {
    var el = ev.target && ev.target.closest
      ? ev.target.closest('a, button, [role="button"], input[type="submit"], input[type="button"], input[type="reset"]')
      : null;
    if (!el) return;
    send("click", el);
  }, true);

  document.addEventListener("input", function (ev) {
    var el = ev.target;
    if (!el || !el.tagName) return;
    var tag = el.tagName.toLowerCase();
    var role = roleOf(el);
    // Only free-text fields stream via input; checkbox/radio/select commit
    // through the change handler below.
    if (tag === "textarea" || (tag === "input" && role === "textbox")) {
      send("type", el, { value: el.value });
    }
  }, true);

  document.addEventListener("change", function (ev) {
    var el = ev.target;
    if (!el || !el.tagName) return;
    var tag = el.tagName.toLowerCase();
    var role = roleOf(el);
    if (role === "checkbox" || role === "radio") {
      send(el.checked ? "check" : "uncheck", el);
    } else if (tag === "select") {
      var opt = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
      send("select", el, { value: opt ? clean(opt.text) : el.value });
    }
  }, true);
})();
"""
