import requests
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


# =========================
# CONFIG
# =========================
BOT_TOKEN = "8930454640:AAH6GyQzVGRzJl9BHt-Oaf99MZHNgkLiI5k"
LTA_API_KEY = "Drd7tmItSyeuI8MFOdlTMA=="
GOOGLE_API_KEY = "AIzaSyBEsORT1mSiQYx0SEJpEKhlda6to4MuZeE"

BUS_STOP_CODE = "44449"

# fixed estimates
LRT_TRAVEL_TIME = 12


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
# 🚆 LRT (LAST TRAIN ONLY)
# =========================
def get_lrt_info():
    last_train = "23:30"
    now = datetime.now().strftime("%H:%M")

    status = "✔ Running"
    if now > last_train:
        status = "❌ Last train already passed"

    return last_train, status, LRT_TRAVEL_TIME


# =========================
# 🚌 LTA BUS (REAL ARRIVALS)
# =========================
def get_bus_lta():
    url = "http://datamall2.mytransport.sg/ltaodataservice/BusArrivalv2"

    headers = {
        "AccountKey": LTA_API_KEY,
        "accept": "application/json"
    }

    params = {"BusStopCode": BUS_STOP_CODE}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)

        if r.status_code != 200:
            return None

        data = r.json()

        for s in data.get("Services", []):
            if s["ServiceNo"] == "67":

                b1 = iso_to_minutes(s["NextBus"]["EstimatedArrival"])
                b2 = iso_to_minutes(s["NextBus2"]["EstimatedArrival"])

                return b1, b2

    except Exception as e:
        print("LTA ERROR:", e)

    return None


# =========================
# 🌐 GOOGLE (BUS TRAVEL ONLY)
# =========================
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


# =========================
# 🧠 BUS ENGINE (HYBRID)
# =========================
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

    # fallback only
    if travel:
        return travel, None, travel + 18, None, "GOOGLE FALLBACK"

    return None, None, None, None, "NO DATA"


# =========================
# ⚡ ROUTE COMPARISON ENGINE
# =========================
def compare_routes():
    lrt_last, lrt_status, lrt_time = get_lrt_info()
    bus1, bus2, bus_total1, bus_total2, source = get_bus_info()

    msg = []

    # 🚆 LRT
    msg.append(f"🚆 LRT Last Train: {lrt_last}")
    msg.append(f"   Status: {lrt_status}")
    msg.append(f"   Travel Time: {lrt_time} min")

    # 🚌 BUS
    if bus1 is not None:
        msg.append(f"\n🚌 Bus 67 Next Wait: {bus1} min")
        msg.append(f"   Total Time: {bus_total1} min")

        if bus2 is not None:
            msg.append(f"🚌 Bus 67 2nd Wait: {bus2} min")
            msg.append(f"   Total Time (2nd): {bus_total2} min")

        msg.append(f"   Source: {source}")
    else:
        msg.append("\n🚌 Bus 67: unavailable")

    # ⚡ FASTEST LOGIC
    if bus_total1 is None:
        fastest = "🚆 LRT"
    else:
        fastest = "🚆 LRT" if lrt_time < bus_total1 else "🚌 Bus 67"

    msg.append(f"\n⚡ Fastest: {fastest}")

    return "\n".join(msg)


# =========================
# 🤖 TELEGRAM HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Transport Bot Ready!\nUse /compare to see fastest route."
    )


async def compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = compare_routes()
    await update.message.reply_text(result)


# =========================
# 🚀 RUN BOT
# =========================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("compare", compare))

    print("Bot running ...")
    app.run_polling(drop_pending_updates=True)