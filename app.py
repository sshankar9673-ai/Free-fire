# server.py – All‑in‑One Flask App with Only 4 Tabs (Rank, Guild, Weapons, Outfit)
# -------------------------------------------------
# Run: python server.py

import asyncio
import time
import httpx
import json
import os
import sys
import threading
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from cachetools import TTLCache
from google.protobuf import json_format
from Crypto.Cipher import AES
import base64
import pickle

# ============= PATH FIX =============
current_dir = os.path.dirname(os.path.abspath(__file__))
proto_dir = os.path.join(current_dir, 'proto')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

try:
    from proto import FreeFire_pb2, main_pb2, AccountPersonalShow_pb2
    print("✅ Proto files imported successfully")
except ImportError:
    try:
        import FreeFire_pb2, main_pb2, AccountPersonalShow_pb2
        print("✅ Proto files imported directly")
    except ImportError as e:
        print(f"❌ Proto import error: {e}")
        sys.exit(1)

# === Settings ===
MAIN_KEY = base64.b64decode('WWcmdGMlREV1aDYlWmNeOA==')
MAIN_IV  = base64.b64decode('Nm95WkRyMjJFM3ljaGpNJQ==')
RELEASEVERSION = "OB53"
USERAGENT = "Dalvik/2.1.0 (Linux; U; Android 13; CPH2095 Build/RKQ1.211119.001)"
REGION_PRIORITY = ["ME", "BD", "IND", "SG", "ID", "TH", "VN", "PK", "BR", "US", "EU"]
SUPPORTED_REGIONS = set(REGION_PRIORITY)
TOKEN_CACHE_FILE = '8247483200:AAGQrYLDPIuhTuSgV55IHoZLHML-lhLFS7w'
IMAGE_BASE_URL = "https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG/"

app = Flask(__name__)
CORS(app)
cache = TTLCache(maxsize=100, ttl=300)
token_manager = None

# === Token Manager (unchanged) ===
class TokenManager:
    def __init__(self):
        self.tokens = {}
        self.lock = asyncio.Lock()
        self.load_tokens()

    def load_tokens(self):
        try:
            if os.path.exists(TOKEN_CACHE_FILE):
                with open(TOKEN_CACHE_FILE, 'rb') as f:
                    saved = pickle.load(f)
                    now = time.time()
                    for r, info in saved.items():
                        if info.get('expires_at', 0) > now:
                            self.tokens[r] = info
                            print(f"✅ Loaded cached token: {r}")
        except Exception as e:
            print(f"❌ Load tokens error: {e}")

    def save_tokens(self):
        try:
            with open(TOKEN_CACHE_FILE, 'wb') as f:
                pickle.dump(dict(self.tokens), f)
        except Exception as e:
            print(f"❌ Save tokens error: {e}")

    async def get_token(self, region: str):
        async with self.lock:
            info = self.tokens.get(region)
            if info and info.get('expires_at', 0) > time.time():
                return info
            new_token = await self.generate_token(region)
            if new_token:
                self.tokens[region] = new_token
                self.save_tokens()
                return new_token
            return None

    async def generate_token(self, region: str):
        try:
            account = get_account_credentials(region)
            token_val, open_id = await get_access_token(account)
            if not token_val or not open_id:
                return None
            body = json.dumps({"open_id": open_id, "open_id_type": "4",
                               "login_token": token_val, "orign_platform_type": "4"})
            proto_bytes = await json_to_proto(body, FreeFire_pb2.LoginReq())
            payload = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, proto_bytes)
            url = "https://loginbp.ggblueshark.com/MajorLogin"
            headers = {
                'User-Agent': USERAGENT, 'Connection': "Keep-Alive",
                'Accept-Encoding': "gzip", 'Content-Type': "application/octet-stream",
                'Expect': "100-continue", 'X-Unity-Version': "2018.4.11f1",
                'X-GA': "v1 1", 'ReleaseVersion': RELEASEVERSION
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, data=payload, headers=headers)
                if resp.status_code != 200:
                    print(f"❌ MajorLogin {resp.status_code} for {region}")
                    return None
                login_res = FreeFire_pb2.LoginRes()
                login_res.ParseFromString(resp.content)
                msg = json.loads(json_format.MessageToJson(login_res))
                token_info = {
                    'token': f"Bearer {msg.get('token','0')}",
                    'region': msg.get('lockRegion','0'),
                    'server_url': msg.get('serverUrl','0'),
                    'expires_at': time.time() + 25200
                }
                print(f"✅ Token generated: {region}")
                return token_info
        except Exception as e:
            print(f"❌ generate_token error [{region}]: {e}")
            return None

    async def refresh_all_tokens(self):
        tasks = [self.get_token(r) for r in REGION_PRIORITY]
        await asyncio.gather(*tasks)
        self.save_tokens()

    async def auto_refresh_loop(self):
        while True:
            await asyncio.sleep(6 * 60 * 60)
            print("🔄 Auto-refreshing all tokens...")
            await self.refresh_all_tokens()

# === Helper Functions ===
def pad(text: bytes) -> bytes:
    n = AES.block_size - (len(text) % AES.block_size)
    return text + bytes([n] * n)

def aes_cbc_encrypt(key, iv, plaintext):
    return AES.new(key, AES.MODE_CBC, iv).encrypt(pad(plaintext))

async def json_to_proto(json_data, proto_message):
    json_format.ParseDict(json.loads(json_data), proto_message)
    return proto_message.SerializeToString()

def get_account_credentials(region: str) -> str:
    r = region.upper()
    if r == "ME":
        return "uid=4269012488&password=MG24_GAMER_U27YB_BY_SPIDEERIO_GAMING_0PNCN"
    elif r == "BD":
        return "uid=4270778393&password=MG24_GAMER_9NMYG_BY_SPIDEERIO_GAMING_FXK8R"
    elif r == "IND":
        return "uid=4269013803&password=MG24_GAMER_XSBOS_BY_SPIDEERIO_GAMING_TE5NG"
    elif r in {"BR", "US", "SAC"}:
        return "uid=4269012488&password=MG24_GAMER_U27YB_BY_SPIDEERIO_GAMING_0PNCN"
    else:
        return "uid=4269012488&password=MG24_GAMER_U27YB_BY_SPIDEERIO_GAMING_0PNCN"

async def get_access_token(account: str):
    url = "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant"
    payload = account + "&response_type=token&client_type=2&client_secret=2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3&client_id=100067"
    headers = {'User-Agent': USERAGENT, 'Content-Type': "application/x-www-form-urlencoded"}
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, data=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("access_token"), data.get("open_id")
                else:
                    print(f"⚠️ Token API attempt {attempt+1}: {resp.status_code}")
                    await asyncio.sleep(2)
        except Exception as e:
            print(f"⚠️ Token API error attempt {attempt+1}: {e}")
            await asyncio.sleep(2)
    return None, None

async def GetAccountInformation(uid, region):
    try:
        token_info = await token_manager.get_token(region)
        if not token_info:
            return None
        token = token_info['token']
        server_url = token_info['server_url']
        payload = await json_to_proto(json.dumps({'a': uid, 'b': '7'}), main_pb2.GetPlayerPersonalShow())
        data_enc = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, payload)
        headers = {
            'User-Agent': USERAGENT, 'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip", 'Content-Type': "application/octet-stream",
            'Expect': "100-continue", 'Authorization': token,
            'X-Unity-Version': "2018.4.11f1", 'X-GA': "v1 1",
            'ReleaseVersion': RELEASEVERSION
        }
        print(f"📡 Requesting info for UID {uid} via {region}...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(server_url + '/GetPlayerPersonalShow', data=data_enc, headers=headers)
            if resp.status_code != 200:
                print(f"❌ API {resp.status_code} for {region}")
                return None
            account_info = AccountPersonalShow_pb2.AccountPersonalShowInfo()
            account_info.ParseFromString(resp.content)
            result = json.loads(json_format.MessageToJson(account_info))
            print(f"✅ Info received for UID {uid} from {region}")
            return result
    except Exception as e:
        print(f"❌ GetAccountInformation error: {e}")
        return None

def format_response(data):
    if not data:
        return {"error": "No data"}
    basic  = data.get("basicInfo", {})
    clan   = data.get("clanBasicInfo", {})
    profile = data.get("profileInfo", {})
    return {
        "AccountInfo": {
            "AccountAvatarId":   str(basic.get("headPic", "0")),
            "AccountBPBadges":   str(basic.get("badgeCnt", "0")),
            "AccountBPID":       str(basic.get("badgeId", "0")),
            "AccountBannerId":   str(basic.get("bannerId", "0")),
            "AccountCreateTime": str(basic.get("createAt", "0")),
            "AccountEXP":        str(basic.get("exp", "0")),
            "AccountLastLogin":  str(basic.get("lastLoginAt", "0")),
            "AccountLevel":      str(basic.get("level", "0")),
            "AccountLikes":      str(basic.get("liked", "0")),
            "AccountName":       basic.get("nickname", "Unknown"),
            "AccountRegion":     basic.get("region", "Unknown"),
            "AccountSeasonId":   str(basic.get("seasonId", "0")),
            "AccountType":       str(basic.get("accountType", "0")),
            "BrMaxRank":         str(basic.get("maxRank", "0")),
            "BrRankPoint":       str(basic.get("rankingPoints", "0")),
            "CsMaxRank":         str(basic.get("csMaxRank", "0")),
            "CsRankPoint":       str(basic.get("csRankingPoints", "0")),
            "EquippedWeapon":    basic.get("weaponSkinShows", []),
            "ReleaseVersion":    basic.get("releaseVersion", RELEASEVERSION),
            "ShowBrRank":        str(basic.get("showBrRank", "0")),
            "ShowCsRank":        str(basic.get("showCsRank", "0")),
            "Title":             str(basic.get("title", "0")),
            "HasElitePass":      str(basic.get("hasElitePass", "0")),
            "IsDeleted":         str(basic.get("isDeleted", "0")),
            "PeriodicRank":      str(basic.get("periodicRank", "0")),
            "PeriodicRankPoints": str(basic.get("periodicRankingPoints", "0")),
            "BrPeakRankPos":     str(basic.get("peakRankPos", "0")),
            "CsPeakRankPos":     str(basic.get("csPeakRankPos", "0")),
        },
        "AccountProfileInfo": {
            "EquippedOutfit": profile.get("clothes", []),
        },
        "GuildInfo": {
            "GuildCapacity": str(clan.get("capacity", "0")),
            "GuildID":       str(clan.get("clanId", "0")),
            "GuildLevel":    str(clan.get("clanLevel", "0")),
            "GuildMember":   str(clan.get("memberNum", "0")),
            "GuildName":     clan.get("clanName", "No Guild"),
            "GuildOwner":    str(clan.get("captainId", "0")),
            "HonorPoint":    str(clan.get("honorPoint", "0")),
        },
        "socialinfo": {}  # not used
    }

# ======================== EMBEDDED HTML WITH LARGER BOTTOM BUTTONS ==========================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>SENKUxFFINFO</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet"/>
<style>
/* ===== RESET ===== */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{
  --ac:#ffd700;
  --ac2:#e6c200;
  --ac-glow:rgba(255,215,0,0.25);
  --bg:#060610;
  --bg2:#0c0c1a;
  --card:#111128;
  --card2:#1a1a3a;
  --border:rgba(255,215,0,0.2);
  --text:#dde8f0;
  --muted:#6a7a8a;
  --gold:#ffd700;
}
html{scroll-behavior:smooth;}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;min-height:100vh;overflow-x:hidden;padding-bottom:90px;} /* extra padding for bigger nav */

/* ===== HACKING CANVAS ===== */
#hackCanvas{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:0.12;}

/* ===== WELCOME BANNER ===== */
#welcomeBanner{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse at center,#08082a 0%,#060610 70%);}
#welcomeBanner.hide{animation:bannerOut 0.8s ease forwards;}
@keyframes bannerOut{to{opacity:0;transform:scale(1.04);}}
.banner-inner{text-align:center;padding:40px 20px;}
.banner-logo{font-size:56px;animation:pulse 2s ease infinite;display:block;margin-bottom:8px;}
@keyframes pulse{0%,100%{filter:drop-shadow(0 0 8px var(--ac));}50%{transform:scale(1.12);filter:drop-shadow(0 0 22px var(--ac));}}
.banner-title{font-family:'Orbitron',monospace;font-size:clamp(11px,2.5vw,18px);color:var(--muted);letter-spacing:8px;margin-bottom:4px;}
.banner-brand{font-family:'Orbitron',monospace;font-size:clamp(26px,7vw,60px);font-weight:900;color:var(--ac);letter-spacing:4px;text-shadow:0 0 20px var(--ac),0 0 40px var(--ac-glow);animation:glitch 4s infinite;}
@keyframes glitch{0%,95%,100%{text-shadow:0 0 20px var(--ac),0 0 40px var(--ac-glow);}96%{text-shadow:-2px 0 #ff0040,2px 0 var(--ac);}97%{text-shadow:2px 0 #ff0040,-2px 0 var(--ac);}98%{text-shadow:0 0 20px var(--ac);}}
.banner-sub{font-family:'Orbitron',monospace;font-size:clamp(10px,2vw,16px);color:var(--muted);letter-spacing:8px;margin-bottom:20px;}
.banner-line{width:0;height:1px;background:linear-gradient(90deg,transparent,var(--ac),transparent);margin:18px auto;animation:lineGrow 1.2s ease 0.3s forwards;}
@keyframes lineGrow{to{width:240px;}}
.banner-tagline{color:var(--muted);font-size:13px;letter-spacing:2px;margin-bottom:28px;}
.banner-btn{background:transparent;color:var(--ac);border:1px solid var(--ac);padding:12px 36px;font-family:'Orbitron',monospace;font-size:12px;font-weight:700;letter-spacing:3px;border-radius:2px;cursor:pointer;box-shadow:0 0 16px var(--ac-glow),inset 0 0 16px rgba(255,215,0,0.05);transition:all 0.3s;}
.banner-btn:hover{background:var(--ac);color:#000;box-shadow:0 0 30px var(--ac);}

/* ===== HEADER ===== */
header{position:sticky;top:0;z-index:100;background:rgba(6,6,16,0.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:12px 16px;}
.header-inner{max-width:1100px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}
.logo-wrap{display:flex;align-items:center;gap:8px;}
.logo-icon{font-size:22px;}
.logo-text{font-family:'Orbitron',monospace;font-size:16px;font-weight:900;color:var(--ac);letter-spacing:2px;text-shadow:0 0 10px var(--ac-glow);}
.logo-accent{color:var(--text);}
.header-right{display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
.header-badge{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:2px;color:var(--ac);border:1px solid var(--border);padding:4px 10px;border-radius:2px;opacity:0.8;}

/* COLOR PICKER */
.color-picker-wrap{display:flex;align-items:center;gap:8px;}
.color-label{font-size:10px;letter-spacing:2px;color:var(--muted);font-family:'Orbitron',monospace;}
.color-swatches{display:flex;gap:5px;}
.swatch{width:18px;height:18px;border-radius:50%;border:2px solid transparent;cursor:pointer;padding:0;transition:all 0.2s;}
.swatch.active{border-color:#fff;transform:scale(1.25);}
.swatch:hover{transform:scale(1.2);}

/* ===== SEARCH ===== */
.search-section{max-width:960px;margin:36px auto 16px;padding:0 14px;position:relative;z-index:1;}
.search-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:28px;box-shadow:0 0 30px var(--ac-glow);}
.search-title{font-family:'Orbitron',monospace;font-size:15px;color:var(--ac);margin-bottom:6px;}
.search-sub{color:var(--muted);font-size:13px;margin-bottom:18px;}
.search-row{display:flex;gap:10px;flex-wrap:wrap;}
.search-row input,.search-row select{flex:1;min-width:170px;background:var(--bg2);border:1px solid var(--border);color:var(--text);padding:11px 14px;border-radius:4px;font-family:'Rajdhani',sans-serif;font-size:15px;outline:none;transition:border-color 0.3s,box-shadow 0.3s;}
.search-row input:focus,.search-row select:focus{border-color:var(--ac);box-shadow:0 0 10px var(--ac-glow);}
.search-row select option{background:var(--card);}
.search-row button{background:transparent;color:var(--ac);border:1px solid var(--ac);padding:11px 26px;font-family:'Orbitron',monospace;font-size:12px;font-weight:700;letter-spacing:2px;border-radius:4px;cursor:pointer;display:flex;align-items:center;gap:8px;transition:all 0.3s;white-space:nowrap;box-shadow:0 0 10px var(--ac-glow);}
.search-row button:hover{background:var(--ac);color:#000;box-shadow:0 0 20px var(--ac);}
.search-row button:disabled{opacity:0.5;cursor:not-allowed;}
.loader{width:14px;height:14px;border:2px solid rgba(255,255,255,0.2);border-top-color:var(--ac);border-radius:50%;animation:spin 0.7s linear infinite;display:inline-block;}
@keyframes spin{to{transform:rotate(360deg);}}

/* ===== ERROR ===== */
.error-box{max-width:960px;margin:12px auto;padding:12px 18px;background:rgba(255,40,40,0.08);border:1px solid rgba(255,60,60,0.35);border-radius:6px;color:#ff7070;font-size:14px;text-align:center;position:relative;z-index:1;display:none;}

/* ===== RESULT ===== */
.result-wrap{max-width:960px;margin:0 auto;padding:0 14px 40px;animation:fadeUp 0.4s ease;position:relative;z-index:1;}
@keyframes fadeUp{from{opacity:0;transform:translateY(16px);}to{opacity:1;transform:translateY(0);}}

/* ===== PLAYER HEADER CARD ===== */
.player-header-card{background:var(--card2);border:1px solid var(--border);border-radius:12px;padding:22px;display:flex;align-items:center;gap:20px;margin-bottom:14px;flex-wrap:wrap;box-shadow:0 0 24px var(--ac-glow);}
.player-avatar{width:100px;height:100px;border-radius:10px;border:2px solid var(--ac);object-fit:cover;box-shadow:0 0 16px var(--ac);background:var(--bg2);}
.player-header-info{flex:1;min-width:200px;}
.player-name{font-family:'Orbitron',monospace;font-size:clamp(16px,3vw,24px);color:var(--ac);margin-bottom:8px;text-shadow:0 0 10px var(--ac-glow);}
.player-tags{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px;}
.tag{padding:3px 10px;border-radius:3px;font-size:11px;font-weight:700;letter-spacing:1px;}
.tag-region{background:rgba(255,215,0,0.1);color:var(--ac);border:1px solid rgba(255,215,0,0.3);}
.tag-level{background:rgba(255,215,0,0.1);color:var(--gold);border:1px solid rgba(255,215,0,0.3);}
.tag-guild{background:rgba(168,85,247,0.1);color:#a855f7;border:1px solid rgba(168,85,247,0.3);}
.player-stats-mini{display:flex;gap:20px;flex-wrap:wrap;}
.stat-mini{display:flex;flex-direction:column;align-items:center;}
.stat-mini-val{font-family:'Orbitron',monospace;font-size:16px;color:var(--ac);font-weight:700;}
.stat-mini-lbl{font-size:10px;color:var(--muted);letter-spacing:1px;}

/* ===== SECTION CARDS (Tab Content) ===== */
.section-card{display:none;}
.section-card.active{display:block;}
.wide-card{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:14px;box-shadow:0 4px 20px rgba(0,0,0,0.4);transition:box-shadow 0.3s;}
.wide-card:hover{box-shadow:0 4px 30px var(--ac-glow);}
.card-header{background:var(--card2);padding:10px 18px;font-family:'Orbitron',monospace;font-size:12px;color:var(--ac);letter-spacing:1px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;}
.card-icon{font-size:14px;}
.info-row-list{display:flex;flex-wrap:wrap;padding:6px 0;}
.info-row{display:flex;flex-direction:column;padding:10px 18px;min-width:140px;border-right:1px solid rgba(255,255,255,0.05);flex:1;}
.info-row:last-child{border-right:none;}
.info-key{font-size:10px;color:var(--muted);letter-spacing:1px;margin-bottom:4px;text-transform:uppercase;}
.info-val{font-size:14px;color:var(--text);font-weight:600;}
.info-val.hl{color:var(--ac);font-family:'Orbitron',monospace;font-size:13px;}

/* ===== EQUIPPED GRIDS ===== */
.equipped-grid{display:flex;flex-wrap:wrap;gap:14px;padding:16px;}
.item-card{background:var(--bg2);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:12px 10px;display:flex;flex-direction:column;align-items:center;gap:8px;transition:all 0.25s;min-width:110px;flex:1 0 auto;max-width:140px;}
.item-card:hover{border-color:var(--ac);box-shadow:0 0 14px var(--ac-glow);transform:translateY(-3px);}
.item-img{width:90px;height:90px;object-fit:contain;border-radius:6px;background:rgba(255,255,255,0.02);padding:4px;}
.item-type{font-size:10px;color:var(--ac);text-align:center;letter-spacing:1px;font-weight:700;}
.empty-msg{color:var(--muted);font-size:13px;padding:16px;width:100%;text-align:center;}

/* ===== HOW TO USE ===== */
.how-btn-wrap{max-width:960px;margin:28px auto;padding:0 14px;text-align:center;position:relative;z-index:1;}
.how-btn{background:transparent;color:var(--ac);border:1px solid var(--border);padding:12px 28px;font-family:'Orbitron',monospace;font-size:11px;font-weight:700;letter-spacing:2px;border-radius:4px;cursor:pointer;transition:all 0.3s;}
.how-btn:hover{border-color:var(--ac);box-shadow:0 0 16px var(--ac-glow);}
.guide-box{max-width:960px;margin:0 auto 36px;padding:0 14px;animation:fadeUp 0.4s ease;position:relative;z-index:1;display:none;}
.guide-inner{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:26px;position:relative;}
.guide-close{position:absolute;top:14px;right:14px;background:rgba(255,255,255,0.07);border:none;color:var(--muted);width:28px;height:28px;border-radius:50%;cursor:pointer;font-size:13px;transition:all 0.2s;}
.guide-close:hover{background:rgba(255,60,60,0.2);color:#ff7070;}
.guide-title{font-family:'Orbitron',monospace;font-size:13px;color:var(--ac);margin-bottom:20px;letter-spacing:1px;}
.guide-lang{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:22px;margin-bottom:18px;}
.guide-block h4{font-size:14px;color:var(--gold);margin-bottom:10px;}
.guide-block ol{list-style:decimal;padding-left:18px;display:flex;flex-direction:column;gap:7px;}
.guide-block li{font-size:13px;color:var(--text);line-height:1.5;}
.guide-block strong{color:var(--ac);}
.guide-note{background:rgba(255,215,0,0.04);border:1px solid rgba(255,215,0,0.15);border-radius:6px;padding:12px;font-size:12px;color:var(--muted);line-height:1.7;}

/* ===== FOOTER ===== */
footer{text-align:center;padding:18px;color:var(--muted);font-size:12px;border-top:1px solid rgba(255,255,255,0.05);position:relative;z-index:1;}

/* ===== BOTTOM TAB BAR (larger buttons) ===== */
.bottom-nav{
  position:fixed;bottom:0;left:0;right:0;z-index:1000;
  background:rgba(6,6,16,0.95);backdrop-filter:blur(12px);
  border-top:1px solid var(--border);
  display:flex;flex-wrap:nowrap;overflow-x:auto;padding:8px 12px;
  gap:10px;justify-content:center;
  box-shadow:0 -4px 20px rgba(0,0,0,0.6);
}
.bottom-nav::-webkit-scrollbar{height:2px;}
.bottom-nav::-webkit-scrollbar-thumb{background:var(--ac);border-radius:2px;}
.nav-tab{
  flex:0 0 auto;padding:10px 20px;border-radius:30px;
  background:transparent;border:1px solid transparent;
  color:var(--muted);font-family:'Rajdhani',sans-serif;
  font-size:15px;font-weight:700;letter-spacing:0.5px;
  cursor:pointer;transition:all 0.2s;white-space:nowrap;
  min-width:80px;text-align:center;
}
.nav-tab:hover{color:var(--text);border-color:var(--border);}
.nav-tab.active{
  color:#000;background:var(--ac);border-color:var(--ac);
  box-shadow:0 0 20px var(--ac-glow);
}
@media(max-width:480px){
  .nav-tab{font-size:13px;padding:8px 14px;min-width:60px;}
  .bottom-nav{gap:6px;padding:6px 8px;}
  body{padding-bottom:75px;}
}
</style>
</head>
<body>

<!-- HACKING CANVAS -->
<canvas id="hackCanvas"></canvas>

<!-- WELCOME BANNER -->
<div id="welcomeBanner">
  <div class="banner-inner">
    <div class="banner-logo">⚡</div>
    <h1 class="banner-title">WELCOME TO</h1>
    <h1 class="banner-brand">SENKUxFFINFO</h1>
    <h2 class="banner-sub">WEBSITE</h2>
    <div class="banner-line"></div>
    <p class="banner-tagline">Free Fire Player Information System</p>
    <button class="banner-btn" onclick="closeBanner()">ENTER SITE &nbsp;▶</button>
  </div>
</div>

<!-- MAIN SITE -->
<div id="mainSite" style="display:none;">

  <header>
    <div class="header-inner">
      <div class="logo-wrap">
        <span class="logo-icon">⚡</span>
        <span class="logo-text">SENKU<span class="logo-accent">xFF</span>INFO</span>
      </div>
      <div class="header-right">
        <div class="color-picker-wrap">
          <span class="color-label">COLOR</span>
          <div class="color-swatches">
            <button class="swatch" data-color="#00ffff" style="background:#00ffff;" title="Cyan" onclick="setThemeColor('#00ffff',this)"></button>
            <button class="swatch" data-color="#ff6b00" style="background:#ff6b00;" title="Orange" onclick="setThemeColor('#ff6b00',this)"></button>
            <button class="swatch" data-color="#00ff87" style="background:#00ff87;" title="Green" onclick="setThemeColor('#00ff87',this)"></button>
            <button class="swatch" data-color="#a855f7" style="background:#a855f7;" title="Purple" onclick="setThemeColor('#a855f7',this)"></button>
            <button class="swatch active" data-color="#ffd700" style="background:#ffd700;" title="Gold" onclick="setThemeColor('#ffd700',this)"></button>
            <button class="swatch" data-color="#ff4fa3" style="background:#ff4fa3;" title="Pink" onclick="setThemeColor('#ff4fa3',this)"></button>
          </div>
        </div>
        <div class="header-badge">FF INFO TOOL</div>
      </div>
    </div>
  </header>

  <section class="search-section">
    <div class="search-card">
      <h2 class="search-title">🔍 Player Info Search</h2>
      <p class="search-sub">Enter Free Fire UID to get full player information</p>
      <div class="search-row">
        <input type="text" id="uidInput" placeholder="Enter Free Fire UID..." maxlength="20"/>
        <select id="regionSelect">
          <option value="">Auto Region</option>
          <option value="ME">ME (Middle East)</option>
          <option value="BD">BD (Bangladesh)</option>
          <option value="IND">IND (India)</option>
          <option value="SG">SG (Singapore)</option>
          <option value="ID">ID (Indonesia)</option>
          <option value="TH">TH (Thailand)</option>
          <option value="VN">VN (Vietnam)</option>
          <option value="PK">PK (Pakistan)</option>
          <option value="BR">BR (Brazil)</option>
          <option value="US">US (USA)</option>
          <option value="EU">EU (Europe)</option>
        </select>
        <button id="searchBtn" onclick="searchPlayer()">
          <span id="btnText">SEARCH</span>
          <span id="btnLoader" class="loader" style="display:none;"></span>
        </button>
      </div>
    </div>
  </section>

  <!-- RESULT SECTION -->
  <section id="resultSection" style="display:none;">
    <div class="result-wrap">

      <!-- Player Header (always visible) -->
      <div class="player-header-card">
        <div class="player-avatar-wrap">
          <img id="playerAvatar" src="" alt="Avatar" class="player-avatar"
               onerror="this.src='https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG/902001.png'"/>
        </div>
        <div class="player-header-info">
          <h2 id="playerName" class="player-name">—</h2>
          <div class="player-tags">
            <span class="tag tag-region" id="tagRegion">—</span>
            <span class="tag tag-level"  id="tagLevel">LV —</span>
            <span class="tag tag-guild"  id="tagGuild">No Guild</span>
          </div>
          <div class="player-stats-mini">
            <div class="stat-mini"><span class="stat-mini-val" id="statLikes">—</span><span class="stat-mini-lbl">Likes</span></div>
            <div class="stat-mini"><span class="stat-mini-val" id="statEXP">—</span><span class="stat-mini-lbl">EXP</span></div>
            <div class="stat-mini"><span class="stat-mini-val" id="statBPBadge">—</span><span class="stat-mini-lbl">BP Badge</span></div>
          </div>
        </div>
      </div>

      <!-- Tab Content: only 4 sections -->
      <div id="section-rank" class="section-card active">
        <div class="wide-card">
          <div class="card-header"><span class="card-icon">🏆</span> Rank Info</div>
          <div class="info-row-list" id="rankInfoList"></div>
        </div>
      </div>

      <div id="section-guild" class="section-card">
        <div class="wide-card">
          <div class="card-header"><span class="card-icon">🏰</span> Guild Info</div>
          <div class="info-row-list" id="guildInfoList"></div>
        </div>
      </div>

      <div id="section-weapons" class="section-card">
        <div class="wide-card">
          <div class="card-header"><span class="card-icon">🔫</span> Equipped Weapon Skins</div>
          <div class="equipped-grid" id="weaponGrid"></div>
        </div>
      </div>

      <div id="section-outfit" class="section-card">
        <div class="wide-card">
          <div class="card-header"><span class="card-icon">👗</span> Equipped Outfit</div>
          <div class="equipped-grid" id="outfitGrid"></div>
        </div>
      </div>

    </div>
  </section>

  <!-- ERROR BOX -->
  <div id="errorBox" class="error-box"><span>❌</span> <span id="errorMsg"></span></div>

  <div class="how-btn-wrap">
    <button class="how-btn" onclick="toggleGuide()">📖 HOW TO USE</button>
  </div>

  <div id="guideBox" class="guide-box">
    <div class="guide-inner">
      <button class="guide-close" onclick="toggleGuide()">✕</button>
      <h3 class="guide-title">📖 How to Use</h3>
      <div class="guide-lang">
        <div class="guide-block">
          <h4>English Guide</h4>
          <ol>
            <li>Open your <strong>Free Fire</strong> game.</li>
            <li>Go to your <strong>Profile</strong> → copy your <strong>UID</strong>.</li>
            <li><strong>Paste the UID</strong> in the search box above.</li>
            <li>Select your <strong>Region</strong> or leave Auto.</li>
            <li>Click <strong>SEARCH</strong> button.</li>
            <li>Full player info appears — use the bottom tabs to switch between Rank, Guild, Weapons, and Outfit.</li>
          </ol>
        </div>
      </div>
      <div class="guide-note">
        <strong>Note:</strong> This tool only shows <em>public</em> profile info. No private data accessed.
      </div>
    </div>
  </div>

  <footer>
    <p>⚡ SENKUxFFINFO &copy; 2024 &nbsp;|&nbsp; Free Fire Player Info Tool &nbsp;|&nbsp; Made with ❤️</p>
  </footer>

  <!-- BOTTOM TAB BAR (only 4 buttons, now larger) -->
  <nav class="bottom-nav" id="bottomNav" style="display:none;">
    <button class="nav-tab active" data-tab="rank" onclick="switchTab('rank')">🏆 Rank</button>
    <button class="nav-tab" data-tab="guild" onclick="switchTab('guild')">🏰 Guild</button>
    <button class="nav-tab" data-tab="weapons" onclick="switchTab('weapons')">🔫 Weapons</button>
    <button class="nav-tab" data-tab="outfit" onclick="switchTab('outfit')">👗 Outfit</button>
  </nav>

</div>

<script>
const IMAGE_BASE = "https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG/";
const PREFIX_MAP = {
  "902":"Avatar","214":"Facepaint","101":"Female Skill","102":"Male Skill",
  "103":"Microchip","905":"Parachute","710":"Bundle","720":"Bundle",
  "203":"Top","204":"Bottom","205":"Shoes","211":"Head","901":"Banner",
  "131":"Pet","130":"Pet/Emote","903":"Loot Box","904":"Backpack",
  "906":"Skyboard","907":"Other","908":"Vehicle","909":"Emote",
  "911":"SkyWings","922":"Skill Skin","912":"Weapon Skin"
};
function getItemType(id){const s=String(id);return PREFIX_MAP[s.slice(0,3)]||PREFIX_MAP[s.slice(0,2)]||"Item";}

/* HACKING CANVAS */
(function initHack(){
  const canvas = document.getElementById('hackCanvas');
  const ctx    = canvas.getContext('2d');
  const chars  = 'アイウエオカキクケコ01アイウエオ10ABCDEF0123456789</>{}[];:#$%^&*|\\SENKUxFFINFO'.split('');
  let cols, drops, fontSize = 13;

  function resize(){
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
    cols  = Math.floor(canvas.width / fontSize);
    drops = Array(cols).fill(1);
  }
  resize();
  window.addEventListener('resize', resize);

  function getColor(){
    return getComputedStyle(document.documentElement).getPropertyValue('--ac').trim() || '#ffd700';
  }

  setInterval(()=>{
    ctx.fillStyle = 'rgba(6,6,16,0.08)';
    ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle = getColor();
    ctx.font = fontSize+'px "Share Tech Mono",monospace';
    for(let i=0;i<drops.length;i++){
      const c = chars[Math.floor(Math.random()*chars.length)];
      ctx.fillText(c, i*fontSize, drops[i]*fontSize);
      if(drops[i]*fontSize > canvas.height && Math.random()>0.975) drops[i]=0;
      drops[i]++;
    }
  }, 45);
})();

/* THEME COLOR */
function hexToRgba(hex, alpha){
  const r=parseInt(hex.slice(1,3),16);
  const g=parseInt(hex.slice(3,5),16);
  const b=parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${alpha})`;
}
function setThemeColor(hex, btn){
  const root = document.documentElement;
  root.style.setProperty('--ac', hex);
  root.style.setProperty('--ac2', hex);
  root.style.setProperty('--ac-glow', hexToRgba(hex, 0.22));
  root.style.setProperty('--border', hexToRgba(hex, 0.2));
  document.querySelectorAll('.swatch').forEach(s=>s.classList.remove('active'));
  if(btn) btn.classList.add('active');
  try{localStorage.setItem('ff_theme_color', hex);}catch(e){}
}
(function loadSavedColor(){
  try{
    const saved = localStorage.getItem('ff_theme_color');
    if(saved){
      setThemeColor(saved);
      document.querySelectorAll('.swatch').forEach(s=>{
        if(s.dataset.color===saved) s.classList.add('active');
        else s.classList.remove('active');
      });
    }
  }catch(e){}
})();

/* BANNER */
function closeBanner(){
  const b=document.getElementById('welcomeBanner');
  b.classList.add('hide');
  setTimeout(()=>{b.style.display='none';document.getElementById('mainSite').style.display='block';},800);
}

/* GUIDE */
function toggleGuide(){
  const g=document.getElementById('guideBox');
  g.style.display = (g.style.display==='none'||g.style.display==='')?'block':'none';
}

/* TAB SWITCHING */
function switchTab(tabId){
  document.querySelectorAll('.section-card').forEach(el=>el.classList.remove('active'));
  const target = document.getElementById('section-'+tabId);
  if(target) target.classList.add('active');
  document.querySelectorAll('.nav-tab').forEach(btn=>{
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
}

/* FORMAT HELPERS */
function fmtTime(ts){
  if(!ts||ts==='0') return '—';
  try{return new Date(parseInt(ts)*1000).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'});}
  catch{return ts;}
}
function fmtNum(n){if(!n||n==='0') return '0'; return parseInt(n).toLocaleString();}

/* BUILD ROWS */
function buildRows(containerId, rows){
  const c = document.getElementById(containerId);
  c.innerHTML='';
  rows.forEach(([key,val,hl])=>{
    const d=document.createElement('div');
    d.className='info-row';
    d.innerHTML=`<span class="info-key">${key}</span><span class="info-val${hl?' hl':''}">${val||'—'}</span>`;
    c.appendChild(d);
  });
}

/* BUILD ITEM GRID */
function buildItemGrid(containerId, ids, emptyMsg){
  const c=document.getElementById(containerId);
  c.innerHTML='';
  const arr=Array.isArray(ids)?ids:[];
  if(!arr.length){c.innerHTML=`<div class="empty-msg">${emptyMsg}</div>`;return;}
  arr.forEach(id=>{
    const sid=String(id);
    const type=getItemType(sid);
    const card=document.createElement('div');
    card.className='item-card';
    card.innerHTML=`
      <img class="item-img" src="${IMAGE_BASE}${sid}.png" alt="${sid}" loading="lazy"
           onerror="this.style.opacity='0.25';this.src='${IMAGE_BASE}902001.png'"/>
      <div class="item-type">${type}</div>`;
    c.appendChild(card);
  });
}

/* RENDER RESULT (only 4 sections) */
function renderResult(data){
  const ai = data.AccountInfo       || {};
  const ap = data.AccountProfileInfo|| {};
  const gi = data.GuildInfo         || {};

  // Player header
  const avatarId = ai.AccountAvatarId||'902001';
  document.getElementById('playerAvatar').src = `${IMAGE_BASE}${avatarId}.png`;
  document.getElementById('playerName').textContent = ai.AccountName||'Unknown';
  document.getElementById('tagRegion').textContent  = ai.AccountRegion||'—';
  document.getElementById('tagLevel').textContent   = `LV ${ai.AccountLevel||'—'}`;
  document.getElementById('tagGuild').textContent   = gi.GuildName||'No Guild';
  document.getElementById('statLikes').textContent  = fmtNum(ai.AccountLikes);
  document.getElementById('statEXP').textContent    = fmtNum(ai.AccountEXP);
  document.getElementById('statBPBadge').textContent= fmtNum(ai.AccountBPBadges);

  // Show bottom nav and result section
  document.getElementById('bottomNav').style.display='flex';
  document.getElementById('resultSection').style.display='block';
  // Default tab: Rank
  switchTab('rank');

  // Rank Info rows
  buildRows('rankInfoList',[
    ['BR Rank Points', fmtNum(ai.BrRankPoint), true],
    ['BR Max Rank',    ai.BrMaxRank],
    ['Show BR Rank',   ai.ShowBrRank==='1'?'✅ Yes':'❌ No'],
    ['BR Peak Pos',    ai.BrPeakRankPos],
    ['CS Rank Points', fmtNum(ai.CsRankPoint), true],
    ['CS Max Rank',    ai.CsMaxRank],
    ['Show CS Rank',   ai.ShowCsRank==='1'?'✅ Yes':'❌ No'],
    ['CS Peak Pos',    ai.CsPeakRankPos],
    ['Periodic Rank',  ai.PeriodicRank],
    ['Periodic Points', fmtNum(ai.PeriodicRankPoints)],
    ['BP ID',          ai.AccountBPID],
  ]);

  // Guild Info rows
  buildRows('guildInfoList',[
    ['Guild Name',  gi.GuildName,  true],
    ['Guild ID',    gi.GuildID],
    ['Level',       gi.GuildLevel],
    ['Members',     `${gi.GuildMember} / ${gi.GuildCapacity}`],
    ['Owner ID',    gi.GuildOwner],
    ['Honor Point', gi.HonorPoint],
  ]);

  // Equipped items
  buildItemGrid('weaponGrid',  ai.EquippedWeapon||[],  '🔫 No weapon skin data');
  buildItemGrid('outfitGrid',  ap.EquippedOutfit||[],  '👗 No outfit data');
}

/* SEARCH */
async function searchPlayer(){
  const uid    = document.getElementById('uidInput').value.trim();
  const region = document.getElementById('regionSelect').value;
  if(!uid){showError('Please enter a UID.');return;}
  if(!/^\\d{5,15}$/.test(uid)){showError('Invalid UID — numbers only.');return;}

  setLoading(true);
  hideError();
  document.getElementById('resultSection').style.display='none';
  document.getElementById('bottomNav').style.display='none';

  try{
    let url=`/get?uid=${encodeURIComponent(uid)}`;
    if(region) url+=`&region=${encodeURIComponent(region)}`;
    const res  = await fetch(url);
    const data = await res.json();
    if(!res.ok||data.error){showError(data.error||'Player not found.');return;}
    renderResult(data);
    document.getElementById('resultSection').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(err){
    showError('Network error.');
    console.error(err);
  }finally{setLoading(false);}
}

function setLoading(on){
  document.getElementById('searchBtn').disabled=on;
  document.getElementById('btnText').style.display   =on?'none':'inline';
  document.getElementById('btnLoader').style.display =on?'inline-block':'none';
}
function showError(msg){
  document.getElementById('errorMsg').textContent=msg;
  document.getElementById('errorBox').style.display='flex';
}
function hideError(){document.getElementById('errorBox').style.display='none';}

document.getElementById('uidInput').addEventListener('keydown',e=>{if(e.key==='Enter')searchPlayer();});
</script>
</body>
</html>
"""

# ======================== FLASK ROUTES ==========================
@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/get')
def get_account_info():
    uid = request.args.get('uid')
    region_param = request.args.get('region', '').upper()
    if not uid:
        return jsonify({"error": "UID required"}), 400

    print(f"\n🔍 Processing info for UID: {uid}")
    print(f"🎯 Region priority: ME -> BD -> IND -> Others")

    regions_to_try = ([region_param] + [r for r in REGION_PRIORITY if r != region_param]
                      if region_param in SUPPORTED_REGIONS else REGION_PRIORITY)

    for region in regions_to_try:
        if region not in token_manager.tokens:
            print(f"⚠️ No token for {region}, skipping...")
            continue
        print(f"🌍 Trying {region}...")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(GetAccountInformation(uid, region))
            loop.close()
            if data:
                print(f"✅ Success with {region}")
                return jsonify(format_response(data))
            else:
                print(f"⚠️ No data from {region}")
        except Exception as e:
            print(f"❌ {region} error: {e}")
            continue

    print("\n❌ All regions failed")
    return jsonify({"error": "Player not found"}), 404

@app.route('/status')
def token_status():
    status = {}
    for region, info in token_manager.tokens.items():
        expires_in = info['expires_at'] - time.time()
        status[region] = {
            "has_token": True,
            "expires_in": f"{expires_in/3600:.1f} hours",
            "server_url": info['server_url'][:50] + "..."
        }
    return jsonify({
        "region_priority": REGION_PRIORITY,
        "total_tokens": len(token_manager.tokens),
        "tokens": status
    })

@app.route('/refresh')
def refresh_tokens():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(token_manager.refresh_all_tokens())
    loop.close()
    return jsonify({"status": "refreshed", "count": len(token_manager.tokens)})

@app.route('/test/<region>')
def test_region(region):
    region = region.upper()
    if region not in SUPPORTED_REGIONS:
        return jsonify({"error": f"Region {region} not supported"})
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    token = loop.run_until_complete(token_manager.get_token(region))
    loop.close()
    if token:
        return jsonify({"region": region, "status": "Token ready",
                        "expires_in": f"{(token['expires_at']-time.time())/3600:.1f} hours"})
    return jsonify({"region": region, "status": "Token generation failed"})

# ======================== STARTUP ==========================
def start_background_tasks():
    global token_manager
    token_manager = TokenManager()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    print("🎯 Generating priority tokens: ME -> BD -> IND")
    for region in ["ME", "IND", "BD"]:
        try:
            loop.run_until_complete(token_manager.get_token(region))
        except Exception as e:
            print(f"⚠️ {region}: {e}")

    other = [r for r in REGION_PRIORITY if r not in ["ME", "BD", "IND"]]
    for region in other:
        try:
            loop.run_until_complete(token_manager.get_token(region))
        except Exception as e:
            print(f"⚠️ {region}: {e}")

    loop.run_forever()

if __name__ == '__main__':
    print("="*55)
    print("🚀 SENKUxFFINFO - Free Fire Info Website")
    print("="*55)
    print(f"🎯 Region Priority: {' -> '.join(REGION_PRIORITY[:3])} -> Others")

    bg = threading.Thread(target=start_background_tasks, daemon=True)
    bg.start()

    print("⏳ Initializing tokens (ME, BD, IND)...")
    time.sleep(10)

    if token_manager:
        print(f"✅ Tokens cached: {len(token_manager.tokens)}")
        for region in REGION_PRIORITY:
            mark = "✓" if region in token_manager.tokens else "✗"
            print(f"  {mark} {region}")

    print("="*55)
    print("🚀 API running on port 5000")
    print("📝 Endpoints:")
    print("   /get?uid=UID        - Get player info")
    print("   /get?uid=UID&region=BD - Specific region")
    print("   /status             - Token status")
    print("   /refresh            - Force refresh")
    print("   /test/REGION        - Test region")
    print("="*55)

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)