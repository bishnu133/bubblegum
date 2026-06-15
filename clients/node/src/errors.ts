/** An error returned by the bridge (a JSON-RPC error response) or a transport failure. */
export class BridgeError extends Error {
  readonly code: number;
  readonly data?: unknown;

  constructor(code: number, message: string, data?: unknown) {
    super(message);
    this.name = "BridgeError";
    this.code = code;
    this.data = data;
  }
}
