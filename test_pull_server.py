#!/usr/bin/env python3
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length:
            return self.rfile.read(length).decode('utf-8')
        return ''

        def do_GET(self):
                # Provide a helpful HTML page when visited in a browser
                html = '''<!doctype html>
<html><head><meta charset="utf-8"><title>Test Pull Server</title></head>
<body>
<h2>Test Pull Server</h2>
<p>This server accepts a <strong>POST</strong> to <code>/api/pull</code> with JSON <code>{"name":"model-name"}</code>.</p>
<p>Use the GUI's Pull button or the form below to simulate a pull.</p>
<form id="f">
    Model name: <input id="m" name="name" value="test-model" />
    <button type="button" onclick="send()">Start Pull</button>
</form>
<pre id="log"></pre>
<script>
function send(){
    const name=document.getElementById('m').value||'test-model';
    const log=document.getElementById('log');
    fetch('/api/pull',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})}).then(r=>{
        if(!r.body){ log.textContent='No streaming body available.'; return }
        const reader=r.body.getReader();
        const dec=new TextDecoder();
        function read(){
            reader.read().then(({done,value})=>{
                if(done){ log.textContent += '\n[done]'; return }
                log.textContent += dec.decode(value);
                read();
            })
        }
        read();
    }).catch(e=>{ log.textContent = 'Error: '+e })
}
</script>
</body></html>
'''
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(html.encode('utf-8'))))
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        if self.path != '/api/pull':
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found')
            return
        body = self._read_body()
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}
        model = data.get('name', 'unknown')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        # Stream a few JSON lines with percent updates
        try:
            for p in range(0, 101, 10):
                payload = {'status': 'downloading', 'percent': p, 'model': model}
                line = json.dumps(payload) + '\n'
                try:
                    self.wfile.write(line.encode('utf-8'))
                    self.wfile.flush()
                except BrokenPipeError:
                    break
                time.sleep(0.25)
            # final
            final = json.dumps({'status': 'finished', 'percent': 100, 'model': model}) + '\n'
            try:
                self.wfile.write(final.encode('utf-8'))
                self.wfile.flush()
            except BrokenPipeError:
                pass
        except Exception:
            pass

if __name__ == '__main__':
    server = HTTPServer(('localhost', 8000), Handler)
    print('Test pull server running on http://localhost:8000 (POST /api/pull)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Shutting down')
        server.server_close()
