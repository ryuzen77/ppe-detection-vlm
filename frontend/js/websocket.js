/**
 * DEPRO - WebSocket Client with auto-reconnect
 */
export class TelemetryWebSocket {
  constructor(url, onMessage, onStatusChange) {
    this.url = url;
    this.onMessage = onMessage;
    this.onStatusChange = onStatusChange;
    this.socket = null;
    this.reconnectTimer = null;
    this.reconnectDelay = 1500;
    this.connect();
  }

  connect() {
    try {
      this.socket = new WebSocket(this.url);

      this.socket.onopen = () => {
        console.log('[WS] Connected to backend telemetry stream');
        this.reconnectDelay = 1500;
        if (this.onStatusChange) this.onStatusChange('connected');
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (this.onMessage) this.onMessage(data);
        } catch (e) {
          console.error('[WS] Parse error:', e);
        }
      };

      this.socket.onclose = () => {
        console.warn('[WS] Connection closed. Retrying...');
        if (this.onStatusChange) this.onStatusChange('disconnected');
        this.scheduleReconnect();
      };

      this.socket.onerror = (err) => {
        console.error('[WS] Socket error:', err);
        this.socket.close();
      };
    } catch (err) {
      console.error('[WS] Connection failed:', err);
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 10000);
      this.connect();
    }, this.reconnectDelay);
  }

  send(data) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data));
    }
  }
}
