import aiohttp
import asyncio
import logging
import json
import config

log = logging.getLogger(__name__)

BASE = config.API_BASE_URL
NAME = config.API_NAME
KEY  = config.API_KEY
PID  = config.PROJECT_ID

async def _get(endpoint: str, params: dict) -> dict:
    params["name"]   = NAME
    params["ApiKey"] = KEY
    url = f"{BASE}/{endpoint}"
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url, params=params) as r:
                text = await r.text()
                log.warning(f"[API] {endpoint} → {text[:200]}")
                try:
                    return json.loads(text)
                except Exception:
                    return {"code": -1, "msg": text}
    except asyncio.TimeoutError:
        log.warning(f"[API] {endpoint} → TIMEOUT")
        return {"code": -1, "msg": "timeout"}
    except Exception as e:
        log.warning(f"[API] {endpoint} → ERROR: {e}")
        return {"code": -1, "msg": str(e)}

async def get_balance_api() -> float:
    res = await _get("getUserInfo", {})
    if res.get("code") == 200:
        try:
            return float(res["data"].get("score", 0))
        except Exception:
            return 0.0
    return 0.0

async def get_whatsapp_number() -> dict | None:
    res = await _get("getMobile", {
        "pid":     PID,
        "num":     "1",
        "serial":  "2",
        "noblack": "0",
    })

    if res.get("code") == 200:
        data = res.get("data", "")

        # الـ API بيرجع الرقم مباشرة كـ string: "+9779868649467"
        if isinstance(data, str) and len(data) > 5:
            number = data.replace("+", "").strip()
            return {"id": number, "number": number}

        # أو كـ list
        if isinstance(data, list) and data:
            item = data[0]
            if isinstance(item, str):
                number = item.replace("+", "").strip()
                return {"id": number, "number": number}
            mobile = (item.get("mobile") or item.get("phone") or item.get("number"))
            if mobile:
                return {"id": str(mobile), "number": str(mobile).replace("+", "")}

        # أو كـ dict
        if isinstance(data, dict):
            mobile = (data.get("mobile") or data.get("phone") or data.get("number"))
            if mobile:
                return {"id": str(mobile), "number": str(mobile).replace("+", "")}

    return None

async def check_otp(mobile: str) -> str | None:
    # نجرب كل الـ endpoints المحتملة
    for endpoint in ["getSmsList", "getSmsCode", "getVerCode", "getSms"]:
        res = await _get(endpoint, {"mobile": mobile})
        # لو رجع HTML يعني الـ endpoint غلط، نكمل
        if isinstance(res.get("msg"), str) and "<html" in res.get("msg","").lower():
            continue
        if res.get("code") == 200:
            data = res.get("data", "")
            if isinstance(data, list) and data:
                item = data[0] if isinstance(data[0], dict) else {}
                code = (item.get("code") or item.get("sms_code") or
                        item.get("content") or item.get("msg_content") or
                        item.get("sms") or item.get("verify_code"))
                if code:
                    log.warning(f"[OTP] found via {endpoint}: {code}")
                    return str(code)
            if isinstance(data, str) and data.strip() and "<" not in data:
                return data.strip()
            if isinstance(data, dict):
                code = (data.get("code") or data.get("sms_code") or
                        data.get("content") or data.get("verify_code"))
                if code:
                    return str(code)
        log.warning(f"[OTP] {endpoint} → code={res.get('code')} msg={res.get('msg','')[:50]}")
    return None

async def release_number(mobile: str) -> bool:
    res = await _get("releaseMobile", {"mobile": mobile})
    return res.get("code") == 200
