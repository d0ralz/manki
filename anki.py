import json
import urllib.request

class AnkiClient:
    def __init__(self, url='http://127.0.0.1:8765', timeout=2):
        self.url = url
        self.timeout = timeout 

    def invoke(self, action, **params):
        request = {"action": action, "version": 6}
        if params: 
            request["params"] = params
            
        try:
            data = json.dumps(request).encode('utf-8')
            req = urllib.request.Request(self.url, data)
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_data = json.load(response)
            
            if not isinstance(response_data, dict) or 'error' not in response_data or 'result' not in response_data:
                raise ValueError('Invalid response from AnkiConnect')
            
            if response_data['error'] is not None:
                raise Exception(response_data['error'])
                
            return True if response_data['result'] is None else response_data['result']
            
        except Exception as e:
            print(f"AnkiConnect Error: {e}")
            return None