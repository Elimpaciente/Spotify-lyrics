from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import spotipy
import hashlib
import hmac
import math
import re
from urllib.parse import urlparse
app = FastAPI(title="Spotify Lyrics API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Configuration
TOKEN_URL = 'https://open.spotify.com/api/token'
SERVER_TIME_URL = 'https://open.spotify.com/api/server-time'
SPOTIFY_HOME_PAGE_URL = "https://open.spotify.com/"
CLIENT_VERSION = "1.2.46.25.g7f189073"
HEADERS = {    
"accept": "application/json",    
"accept-language": "en-US",    
"content-type": "application/json",    
"origin": SPOTIFY_HOME_PAGE_URL,    
"priority": "u=1, i",    
"referer": SPOTIFY_HOME_PAGE_URL,    
"sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',    
"sec-ch-ua-mobile": "?0",    
"sec-ch-ua-platform": '"Windows"',    
"sec-fetch-dest": "empty",    
"sec-fetch-mode": "cors",    
"sec-fetch-site": "same-site",    
"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",    
"spotify-app-version": CLIENT_VERSION,    
"app-platform": "WebPlayer",
}
DEFAULT_SP_DC = "AQAO1j7bPbFcbVh5TbQmwmTd_XFckJhbOipaA0t2BZpViASzI6Qrk1Ty0WviN1K1mmJv_hV7xGVbMPHm4-HAZbs3OXOHSu38Xq7hZ9wqWwvdZwjiWTQmKWLoKxJP1j3kI7-8eWgVZ8TcPxRnXrjP3uDJ9SnzOla_EpxePC74dHa5D4nBWWfFLdiV9bMQuzUex6izb12gCh0tvTt3Xlg"
class TOTP:    
def __init__(self) -> None:
        self.secret, self.version = self.get_secret_version()
        self.period = 30
        self.digits = 6
    def generate(self, timestamp: int) -> str:
        counter = math.floor(timestamp / 1000 / self.period)
        counter_bytes = counter.to_bytes(8, byteorder="big")
        h = hmac.new(self.secret, counter_bytes, hashlib.sha1)
        hmac_result = h.digest()
        offset = hmac_result[-1] & 0x0F
        binary = (            
(hmac_result[offset] & 0x7F) << 24
            | (hmac_result[offset + 1] & 0xFF) << 16
            | (hmac_result[offset + 2] & 0xFF) << 8
            | (hmac_result[offset + 3] & 0xFF)        
)
        return str(binary % (10**self.digits)).zfill(self.digits)        
def get_secret_version(self) -> tuple:        
try:
            req = requests.get(                
"https://raw.githubusercontent.com/Thereallo1026/spotify-secrets/refs/heads/main/secrets/secrets.json",
                timeout=10            
)            
if req.status_code != 200:                
raise ValueError("Failed to fetch TOTP secret and version.")
            data = req.json()[-1]
            ascii_codes = [ord(c) for c in data['secret']]
            transformed = [val ^ ((i % 33) + 9) for i, val in enumerate(ascii_codes)]
            secret_key = "".join(str(num) for num in transformed)            
return bytes(secret_key, 'utf-8'), data['version']        
except Exception as e:            
raise ValueError(f"Failed to fetch TOTP secret: {str(e)}")
class SpotifyLyricsAPI:    
def __init__(self, sp_dc: str = DEFAULT_SP_DC) -> None:
        self.session = requests.Session()
        self.session.cookies.set('sp_dc', sp_dc)
        self.session.headers.update(HEADERS)
        self.totp = TOTP()
        self._login()
        self.sp = spotipy.Spotify(auth=self.token)
    def _login(self):        
try:
            server_time_response = self.session.get(SERVER_TIME_URL, timeout=10)
            server_time = 1e3 * server_time_response.json()["serverTime"]
            totp = self.totp.generate(timestamp=server_time)
            params = {                
"reason": "init",                
"productType": "web-player",                
"totp": totp,
