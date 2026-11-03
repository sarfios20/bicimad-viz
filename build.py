#!/usr/bin/env python3
"""Procesa los datos crudos de data/ y genera web/data.js para el dashboard."""
import csv
import io
import json
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "web" / "data.js"

MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


def load_stations():
    info = json.loads((DATA / "station_information.json").read_text())["data"]["stations"]
    status = json.loads((DATA / "station_status.json").read_text())["data"]["stations"]
    by_id = {s["station_id"]: s for s in status}
    stations = []
    for s in info:
        st = by_id.get(s["station_id"], {})
        stations.append({
            "id": s["station_id"],
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "capacity": s.get("capacity", 0),
            "bikes": st.get("num_bikes_available", 0),
            "docks": st.get("num_docks_available", 0),
            "disabled": st.get("num_bikes_disabled", 0),
            "inService": st.get("status") == "IN_SERVICE",
        })
    ts = json.loads((DATA / "station_status.json").read_text())["last_updated"]
    return stations, ts


def load_daily():
    rows = []
    with open(DATA / "viajes_diarios.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            d = row["FECHA"].strip()
            if not d:
                continue
            rows.append({"date": d, "trips": int(row["VIAJES"])})
    rows.sort(key=lambda r: r["date"])
    return rows


def load_users():
    rows = []
    with open(DATA / "usuarios_activos.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            d = row["FECHA"].strip()
            if not d:
                continue
            day, month, year = d.split("/")
            rows.append({"date": f"{year}-{month}-{day}",
                         "users": int(row["USUARIOS ACTIVOS"])})
    rows.sort(key=lambda r: r["date"])
    return rows


def monthly_totals(daily):
    """Totales por mes agrupados por año: {year: [12 valores o null]}"""
    acc = {}
    for r in daily:
        y, m, _ = r["date"].split("-")
        acc.setdefault(y, [None] * 12)
        i = int(m) - 1
        acc[y][i] = (acc[y][i] or 0) + r["trips"]
    return acc


def weekday_avg(daily):
    """Media de viajes por día de la semana (lun..dom)."""
    sums = [0] * 7
    counts = [0] * 7
    for r in daily:
        wd = date.fromisoformat(r["date"]).weekday()
        sums[wd] += r["trips"]
        counts[wd] += 1
    return [round(s / c) if c else 0 for s, c in zip(sums, counts)]


def heatmap(daily):
    """Media de viajes por (mes, día de semana) sobre todo el periodo."""
    sums = {}
    counts = {}
    for r in daily:
        d = date.fromisoformat(r["date"])
        key = (d.month - 1, d.weekday())
        sums[key] = sums.get(key, 0) + r["trips"]
        counts[key] = counts.get(key, 0) + 1
    grid = [[None] * 7 for _ in range(12)]
    for (m, wd), s in sums.items():
        grid[m][wd] = round(s / counts[(m, wd)])
    return grid


def load_distritos(max_pts_per_ring=160):
    """Decodifica el TopoJSON de distritos del geoportal a anillos lon/lat simplificados."""
    t = json.loads((DATA / "distritos.topojson").read_text())
    sx, sy = t["transform"]["scale"]
    tx, ty = t["transform"]["translate"]

    arcs = []
    for arc in t["arcs"]:
        pts, x, y = [], 0, 0
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring_coords(arc_idxs):
        ring = []
        for idx in arc_idxs:
            pts = arcs[~idx][::-1] if idx < 0 else arcs[idx]
            ring.extend(pts if not ring else pts[1:])
        step = max(1, len(ring) // max_pts_per_ring)
        out = ring[::step]
        if out[-1] != ring[-1]:
            out.append(ring[-1])
        return [[round(p[0], 5), round(p[1], 5)] for p in out]

    distritos = []
    for g in t["objects"]["Distritos"]["geometries"]:
        polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        rings = [ring_coords(poly[0]) for poly in polys]  # solo anillo exterior
        distritos.append({"name": g["properties"]["NOMBRE"], "rings": rings})
    return distritos


TRIP_FIELDS = ("unlock_date", "lock_date", "unlock_station_name",
               "lock_station_name", "geolocation_unlock")


def station_num(name):
    """'27 - Huertas' -> '27' (None si no cuadra el patrón)."""
    if not name:
        return None
    head = name.split(" - ", 1)[0].strip()
    return head if head.replace("a", "").replace("b", "").isdigit() else head or None


def _aggregate_month(args):
    """Cuenta salidas/llegadas por (estación, tipo de día, hora) en un mes."""
    outer_zip, inner_name, year = args
    outs = defaultdict(int)
    ins = defaultdict(int)
    days = {"wd": set(), "we": set()}
    names = {}
    geo = {}
    with zipfile.ZipFile(outer_zip) as z:
        inner = io.BytesIO(z.read(inner_name))
    with zipfile.ZipFile(inner) as z:
        csv_name = next(n for n in z.namelist()
                        if n.endswith(".csv") and "__MACOSX" not in n)
        with z.open(csv_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                                    delimiter=";")
            for row in reader:
                for side, acc in (("unlock", outs), ("lock", ins)):
                    ts = row.get(f"{side}_date") or ""
                    if len(ts) < 13 or not ts.startswith(year):
                        continue
                    num = station_num(row.get(f"{side}_station_name"))
                    if not num:
                        continue
                    try:
                        d = date.fromisoformat(ts[:10])
                        hour = int(ts[11:13])
                    except ValueError:
                        continue
                    typ = "we" if d.weekday() >= 5 else "wd"
                    acc[(num, typ, hour)] += 1
                    days[typ].add(ts[:10])
                    if num not in names:
                        names[num] = row.get(f"{side}_station_name")
                        gl = row.get("geolocation_unlock") or ""
                        i = gl.find("[")
                        if i >= 0 and side == "unlock":
                            try:
                                lon, lat = gl[i + 1:gl.find("]")].split(",")
                                geo[num] = (float(lat), float(lon))
                            except ValueError:
                                pass
    return dict(outs), dict(ins), days, names, geo


def load_flow(year_zip):
    """Media de salidas/llegadas por estación y hora (laborable/finde) de un año de viajes."""
    with zipfile.ZipFile(year_zip) as z:
        months = sorted(n for n in z.namelist()
                        if "-csv.zip" in n and "__MACOSX" not in n)
    year = year_zip.stem.split("_")[-1]
    with Pool(min(12, len(months))) as pool:
        results = pool.map(_aggregate_month, [(year_zip, m, year) for m in months])

    outs = defaultdict(int)
    ins = defaultdict(int)
    days = {"wd": set(), "we": set()}
    names = {}
    geo = {}
    for o, i, d, n, g in results:
        for k, v in o.items():
            outs[k] += v
        for k, v in i.items():
            ins[k] += v
        for typ in days:
            days[typ] |= d[typ]
        for num, name in n.items():
            names.setdefault(num, name)
        for num, coords in g.items():
            geo.setdefault(num, coords)

    n_wd, n_we = len(days["wd"]), len(days["we"])
    gbfs = json.loads((DATA / "station_information.json").read_text())["data"]["stations"]
    gbfs_by_num = {station_num(s["name"]): s for s in gbfs}

    stations = []
    for num in sorted(names, key=lambda x: (len(x), x)):
        cur = gbfs_by_num.get(num)
        lat, lon = (cur["lat"], cur["lon"]) if cur else geo.get(num, (None, None))
        if lat is None:
            continue
        def series(acc, typ, n_days):
            return [round(acc.get((num, typ, h), 0) / n_days, 1) for h in range(24)]
        stations.append({
            "num": num,
            "name": names[num],
            "lat": lat, "lon": lon,
            "wdOut": series(outs, "wd", n_wd), "wdIn": series(ins, "wd", n_wd),
            "weOut": series(outs, "we", n_we), "weIn": series(ins, "we", n_we),
        })
    total = sum(outs.values())
    return {"year": year, "stations": stations,
            "totalTrips": total, "daysWd": n_wd, "daysWe": n_we}


def main():
    stations, live_ts = load_stations()
    daily = load_daily()
    users = load_users()
    distritos = load_distritos()
    flow_zip = DATA / "bicimad_2022.zip"
    flow = load_flow(flow_zip) if flow_zip.exists() else None

    payload = {
        "distritos": distritos,
        "flow": flow,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "liveTimestamp": time.strftime("%Y-%m-%d %H:%M", time.localtime(live_ts)),
        "stations": stations,
        "daily": daily,
        "users": users,
        "monthly": monthly_totals(daily),
        "weekdayAvg": weekday_avg(daily),
        "heatmap": heatmap(daily),
        "meses": MESES,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("window.BICIMAD = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    n_bikes = sum(s["bikes"] for s in stations)
    print(f"OK -> {OUT}")
    print(f"  {len(stations)} estaciones, {n_bikes} bicis disponibles ahora")
    print(f"  {len(daily)} días de viajes ({daily[0]['date']} .. {daily[-1]['date']})")
    print(f"  {len(users)} meses de usuarios activos")
    print(f"  {len(distritos)} distritos")
    if flow:
        print(f"  flujo {flow['year']}: {len(flow['stations'])} estaciones, "
              f"{fmt_int(flow['totalTrips'])} viajes ({flow['daysWd']} laborables + {flow['daysWe']} finde)")


def fmt_int(n):
    return f"{n:,}".replace(",", ".")


if __name__ == "__main__":
    main()
