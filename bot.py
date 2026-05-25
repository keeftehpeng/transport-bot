import os
import requests
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
LTA_API_KEY = os.getenv("LTA_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

BUS_STOP_CODE = "44449"
LRT_WALK_TIME = 5
LRT_STATION_CODE = "DT1"
LRT_TRAVEL_TIME_FALLBACK = 12

# =========================
# UTIL
# =========================
def iso_to_minutes(iso_time):
    try:
        t = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, int((t - now).total_seconds() / 60))
    except:
        return None

# =========================
# LRT
# =========================
def get_lrt_info():
    last_train = "23:30"
    now = datetime.now().strftime("%H:%M")
    status = "✔ Running"
    if now > last_train:
        status = "❌ Last train already passed"

    url = "https://datamall2.mytransport.sg/ltaodataservice/v3/TrainArrival"
    headers = {"AccountKey": LTA_API_KEY, "accept": "application/json"}
    params = {"StationCode": LRT_STATION_CODE}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
        if r.status_code != 200:
            print(f"LRT API ERROR: status={r.status_code}, body={r.text}")
            return last_train, status, LRT_TRAVEL_TIME_FALLBACK + LRT_WALK_TIME

        data = r.json()
        services = data.get("Services", [])

        if services:
            next_train = services[0].get("NextTrain", {})
            arrival_iso = next_train.get("EstimatedArrival", "")
            wait = iso_to_minutes(arrival_iso)

            if wait is not None:
                total = wait + LRT_WALK_TIME
                return last_train, status, total

    except Exception as e:
        print("LRT API ERROR:", e)

    return last_train, status, LRT_TRAVEL_TIME_FALLBACK + LRT_WALK_TIME

# =========================
# BUS
# =========================
def get_bus_lta():
    url = "https://datamall2.mytransport.sg/ltaodataservice/v3/BusArrival"
    headers = {"AccountKey": LTA_API_KEY, "accept": "application/json"}
    params = {"BusStopCode": BUS_STOP_CODE}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
        if r.status_code != 200:
            print(f"LTA BUS ERROR: status={r.status_code}, body={r.text}")
            return None
        data = r.json()
        for s in data.get("Services", []):
            if s["ServiceNo"] == "67":
                b1 = iso_to_minutes(s["NextBus"]["EstimatedArrival"])
                b2 = iso_to_minutes(s["NextBus2"]["EstimatedArrival"])
                return b1, b2
    except Exception as e:
        print("LTA BUS ERROR:", e)
    return None

def get_bus_google_travel_only():
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": "Bukit Panjang MRT Singapore",
        "destination": "Keat Hong Singapore",
        "mode": "transit",
        "transit_mode": "bus",
        "key": GOOGLE_API_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()
        if data.get("status") != "OK":
            return None
        return data["routes"][0]["legs"][0]["duration"]["value"] // 60
    except:
        return None

def get_bus_info():
    lta = get_bus_lta()
    travel = get_bus_google_travel_only()
    if lta:
        wait1, wait2 = lta
        source = "LTA LIVE"
        if travel:
            total1 = wait1 + travel
            total2 = wait2 + travel if wait2 else None
        else:
            total1 = wait1 + 18
            total2 = None
        return wait1, wait2, total1, total2, source
    if travel:
        return travel, None, travel + 18, None, "GOOGLE FALLBACK"
    return None, None, None, None, "NO DATA"

# =========================
# COMPARE
# =========================
def compare_routes():
    lrt_last, lrt_status, lrt_time = get_lrt_info()
    bus1, bus2, bus_total1, bus_total2, source = get_bus_info()

    msg = []
    msg.append(f"🚆 LRT Last Train: {lrt_last}")
    msg.append(f"   Status: {lrt_status}")
    msg.append(f"   Total Time (incl. walk): {lrt_time} min")

    if bus1 is not None:
        msg.append(f"\n🚌 Bus 67 Next Wait: {bus1} min")
        msg.append(f"   Total Time: {bus_total1} min")
        if bus2 is not None:
            msg.append(f"🚌 Bus 67 2nd Wait: {bus2} min")
            msg.append(f"   Total Time (2nd): {bus_total2} min")
        msg.append(f"   Source: {source}")
    else:
        msg.append("\n🚌 Bus 67: unavailable")

    fastest = "🚆 LRT" if bus_total1 is None else ("🚆 LRT" if lrt_time < bus_total1 else "🚌 Bus 67")
    msg.append(f"\n⚡ Fastest: {fastest}")

    result = "\n".join(msg)
    print(f"DEBUG result: '{result}'")
    return result

# =========================
# TELEGRAM HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Transport Bot Ready!\nUse /compare to see fastest route."
    )

async def compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = compare_routes()
    await update.message.reply_text(result)

# =========================
# RUN BOT (WEBHOOK)
# =========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("compare", compare))

    print("Bot running via webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="webhook",
        webhook_url=f"{WEBHOOK_URL}/webhook",
    )
