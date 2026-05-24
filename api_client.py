import aiohttp
import config

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
            try:
                return await r.json(content_type=None)
            except Exception:
                return {"code": -1, "msg": await r.text()}

async def get_balance_api() -> float:
    """رصيد الحساب على durianrcs"""
    res = await _get("getUserInfo", {})
    if res.get("code") == 200:
        return float(res["data"].get("score", 0))
    return 0.0

async def get_whatsapp_number() -> dict | None:
    """
    يطلب رقم عشوائي من durianrcs
    الرد: {"id": "...", "number": "..."} أو None
    """
    res = await _get("getMobile", {
        "pid":     PID,
        "num":     "1",
        "serial":  "2",      # 2 = رقم واحد
        "noblack": "0",
    })
    if res.get("code") == 200:
        data = res.get("data", {})
        # الرقم ممكن يجي كـ list أو dict
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            return None
        mobile = item.get("mobile") or item.get("phone") or item.get("number")
        mid    = item.get("id") or item.get("mid") or mobile
        if mobile:
            return {"id": str(mid), "number": str(mobile)}
    return None

async def check_otp(mobile: str) -> str | None:
    """
    يتحقق من وصول الـ OTP للرقم
    يرجع: الكود أو None إذا ما وصل بعد
    """
    res = await _get("getSms", {"mobile": mobile})
    if res.get("code") == 200:
        data = res.get("data", {})
        if isinstance(data, list) and data:
            data = data[0]
        code = (data.get("code") or data.get("sms_code")
                or data.get("content") or data.get("msg_content"))
        if code:
            return str(code)
    return None

async def release_number(mobile: str) -> bool:
    """يحرر الرقم ويرجع الرصيد"""
    res = await _get("releaseMobile", {"mobile": mobile})
    return res.get("code") == 200
