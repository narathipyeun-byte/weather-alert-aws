import json
import urllib.parse
import urllib.request

HOURLY = "temperature_2m,precipitation_probability,precipitation,wind_speed_10m,uv_index"
DAILY = ("temperature_2m_max,temperature_2m_min,precipitation_sum,"
         "precipitation_probability_max,wind_speed_10m_max,uv_index_max")


def fetch_forecast(lat, lon):
    query = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature",
        "hourly": HOURLY, "daily": DAILY,
        "timezone": "Asia/Bangkok", "forecast_days": 7,
    })
    url = "https://api.open-meteo.com/v1/forecast?" + query
    with urllib.request.urlopen(url, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))


def make_flags(rain, t_min, t_max, wind, uv):
    return {"rain": rain, "cold": t_min <= 22, "hot": t_max >= 36,
            "wind": wind >= 30, "uv": uv >= 8}


def compute(d):
    """Same rules as the web page: next 24 hours + 7 daily rows."""
    t0 = d["current"]["time"][:13] + ":00"
    start = next(i for i, t in enumerate(d["hourly"]["time"]) if t >= t0)

    def pick(key):
        return [x or 0 for x in d["hourly"][key][start:start + 24]]

    prob, rain_mm = pick("precipitation_probability"), pick("precipitation")
    temp, wind, uv = pick("temperature_2m"), pick("wind_speed_10m"), pick("uv_index")
    prob_avg6 = int(sum(prob[:6]) / 6 + 0.5)
    rain_total = round(sum(rain_mm), 1)

    result = {
        "now": d["current"]["temperature_2m"],
        "feels": d["current"]["apparent_temperature"],
        "tMin": min(temp), "tMax": max(temp),
        "probAvg6": prob_avg6, "rainMm": rain_total,
        "windMax": max(wind), "uvMax": max(uv),
        "prob": prob, "hours": d["hourly"]["time"][start:start + 24],
    }
    result["flags"] = make_flags(prob_avg6 >= 60 or rain_total >= 1,
                                 result["tMin"], result["tMax"],
                                 result["windMax"], result["uvMax"])

    days, dl = [], d["daily"]
    for i, date in enumerate(dl["time"]):
        p = dl["precipitation_probability_max"][i] or 0
        mm = dl["precipitation_sum"][i] or 0
        row = {"date": date, "tMax": dl["temperature_2m_max"][i],
               "tMin": dl["temperature_2m_min"][i], "prob": p, "mm": mm,
               "wind": dl["wind_speed_10m_max"][i], "uv": dl["uv_index_max"][i]}
        row["flags"] = make_flags(p >= 60 or mm >= 1, row["tMin"], row["tMax"],
                                  row["wind"], row["uv"])
        days.append(row)
    result["days"] = days
    return result


def reply(code, body):
    return {"statusCode": code,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps(body, ensure_ascii=False)}


def lambda_handler(event, context):
    q = event.get("queryStringParameters") or {}
    try:
        lat, lon = float(q["lat"]), float(q["lon"])
        if not (5 <= lat <= 21 and 97 <= lon <= 106):
            raise ValueError("outside Thailand")
    except (KeyError, ValueError):
        return reply(400, {"error": "ต้องส่ง lat และ lon ของประเทศไทย เช่น ?lat=13.75&lon=100.5"})
    try:
        return reply(200, compute(fetch_forecast(lat, lon)))
    except Exception as e:
        return reply(502, {"error": "ดึงข้อมูลพยากรณ์ไม่สำเร็จ: " + str(e)})
