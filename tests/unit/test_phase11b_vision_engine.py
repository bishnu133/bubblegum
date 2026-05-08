from bubblegum.core.vision.engine import FakeVisionProvider, VisionCandidate, build_vision_candidates_from_screenshot, normalize_vision_candidates

def test_normalize_valid_vision_candidates_from_dict_and_dataclass():
    out = normalize_vision_candidates([{"label":" Login ","bbox":[1.2,2,30,40],"confidence":1.4,"role":" button ","text":" Sign in "}, VisionCandidate(label="Submit", bbox=(5,6,7,8), confidence=-0.2, role="cta", text="Go")])
    assert len(out)==2
    assert out[0].label=="Login" and out[0].bbox==[1,2,30,40] and out[0].confidence==1.0 and out[0].role=="button" and out[0].text=="Sign in"
    assert out[1].bbox==[5,6,7,8] and out[1].confidence==0.0

def test_normalize_drops_malformed_or_empty_candidates():
    out = normalize_vision_candidates([{}, {"label":"   "}, {"label":"ok","bbox":[1,2,3]}, {"label":"ok","bbox":[1,"x",3,4]}, {"label":"ok","confidence":"bad"}])
    assert len(out)==1 and out[0].label=="ok" and out[0].confidence==0.0

def test_fake_provider_deterministic_output():
    p=FakeVisionProvider()
    a=p.detect_targets(b"png","Click Login")
    b=p.detect_targets(b"png","Click Login")
    assert a==b and a[0]["bbox"]==[10,20,110,70]

def test_pipeline_returns_empty_when_disabled_or_gated_or_missing_inputs():
    p=FakeVisionProvider()
    assert build_vision_candidates_from_screenshot(b"png",instruction="x",provider=p,enabled=False,privacy_gate=True)==[]
    assert build_vision_candidates_from_screenshot(b"png",instruction="x",provider=p,enabled=True,privacy_gate=False)==[]
    assert build_vision_candidates_from_screenshot(None,instruction="x",provider=p,enabled=True,privacy_gate=True)==[]
    assert build_vision_candidates_from_screenshot(b"png",instruction="x",provider=None,enabled=True,privacy_gate=True)==[]

class _RaisingProvider:
    def detect_targets(self, image_bytes: bytes, instruction: str, context=None):
        raise RuntimeError("boom")

def test_pipeline_returns_empty_when_provider_raises():
    assert build_vision_candidates_from_screenshot(b"png",instruction="click",provider=_RaisingProvider(),enabled=True,privacy_gate=True)==[]

def test_pipeline_returns_normalized_candidates_when_enabled():
    out=build_vision_candidates_from_screenshot(b"png",instruction="Click Login",provider=FakeVisionProvider(),enabled=True,privacy_gate=True)
    assert len(out)==1 and out[0].label=="Click Login" and out[0].confidence==0.82
