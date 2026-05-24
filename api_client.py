import aiohttp
import logging
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
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params) as r:
            text = await r.text()
            log.warning(f"[API] {endpoint} → {text}")  # عشان نشوف الرد
            try:
                import json
                return json.loads(text)
            except Exception:
                return {"code": -1, "msg": text}

async def get_balance_api() -> float:
    res = await _get("getUserInfo", {})
    if res.get("code") == 200:
        return float(res["data"].get("score", 0))
    return 0.0

async def get_whatsapp_number() -> dict | None:
    res = await _get("getMobile", {
        "pid":     PID,
        "num":     "1",
        "serial":  "2",
        "noblack": "0",
    })
    log.warning(f"[getMobile full response] {res}")

    if res.get("code") == 200:
        data = res.get("data", {})
        # جرب كل الاحتمالات
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            log.warning(f"[getMobile] data format unknown: {data}")
            return None

        mobile = (item.get("mobile") or item.get("phone") or
                  item.get("number") or item.get("tel"))
        mid    = (item.get("id") or item.get("mid") or
                  item.get("uuid") or mobile)

        log.warning(f"[getMobile] mobile={mobile}, id={mid}")
        if mobile:
            return {"id": str(mid), "number": str(mobile)}

    log.warning(f"[getMobile] failed, code={res.get('code')}, msg={res.get('msg')}")
    return None

async def check_otp(mobile: str) -> str | None:
    res = await _get("getSms", {"mobile": mobile})
    if res.get("code") == 200:
        data = res.get("data", {})
        if isinstance(data, list) and data:
            data = data[0]
        code = (data.get("code") or data.get("sms_code") or
                data.get("content") or data.get("msg_content"))
        if code:
            return str(code)
    return None

async def release_number(mobile: str) -> bool:
    res = await _get("releaseMobile", {"mobile": mobile})
    return res.get("code") == 200
