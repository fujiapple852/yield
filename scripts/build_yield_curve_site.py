#!/usr/bin/env python3
import argparse
import csv
import html
import json
import math
import re
import shutil
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "public"
DEFAULT_DATA_FILE = ROOT / "data" / "us_treasury_yield_curve_history.csv"
DEFAULT_ASSETS_DIR = ROOT / "assets"
DATA_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)

MATURITIES = [
    ("1M", "BC_1MONTH"),
    ("2M", "BC_2MONTH"),
    ("3M", "BC_3MONTH"),
    ("4M", "BC_4MONTH"),
    ("6M", "BC_6MONTH"),
    ("1Y", "BC_1YEAR"),
    ("2Y", "BC_2YEAR"),
    ("3Y", "BC_3YEAR"),
    ("5Y", "BC_5YEAR"),
    ("7Y", "BC_7YEAR"),
    ("10Y", "BC_10YEAR"),
    ("20Y", "BC_20YEAR"),
    ("30Y", "BC_30YEAR"),
]


def local_name(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_float(value):
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_year(year):
    url = DATA_URL.format(year=year)
    req = urllib.request.Request(url, headers={"User-Agent": "codex-yield-curve-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    rows = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        props = entry.find(
            "{http://www.w3.org/2005/Atom}content/"
            "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties"
        )
        if props is None:
            continue
        values = {local_name(child.tag): child.text for child in props}
        raw_date = values.get("NEW_DATE")
        if not raw_date:
            continue
        day = raw_date[:10]
        rates = [parse_float(values.get(field)) for _, field in MATURITIES]
        if any(rate is not None for rate in rates):
            rows.append({"date": day, "rates": rates})
    return rows


def fetch_years(start_year=1990, end_year=None):
    end_year = end_year or date.today().year
    all_rows = []
    for year in range(start_year, end_year + 1):
        print(f"Fetching {year}...", file=sys.stderr, flush=True)
        rows = fetch_year(year)
        all_rows.extend(rows)
        time.sleep(0.15)
    return all_rows


def merge_rows(existing_rows, fetched_rows):
    by_date = {row["date"]: row for row in existing_rows}
    for row in fetched_rows:
        by_date[row["date"]] = row
    return [by_date[day] for day in sorted(by_date)]


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = ["date", *[label for label, _ in MATURITIES]]
        if reader.fieldnames != expected:
            raise SystemExit(f"Unexpected CSV header in {path}: {reader.fieldnames}")
        rows = []
        for record in reader:
            rows.append(
                {
                    "date": record["date"],
                    "rates": [parse_float(record[label]) for label, _ in MATURITIES],
                }
            )
    return rows


def y_domain(rows):
    values = [rate for row in rows for rate in row["rates"] if rate is not None]
    raw_low = math.floor((min(values) - 0.15) * 2) / 2
    low = 0 if min(values) >= 0 else raw_low
    high = math.ceil((max(values) + 0.15) * 2) / 2
    return [low, high]


def coverage(rows):
    result = []
    for idx, (label, _) in enumerate(MATURITIES):
        dated = [row["date"] for row in rows if row["rates"][idx] is not None]
        result.append(
            {
                "label": label,
                "first": dated[0] if dated else None,
                "last": dated[-1] if dated else None,
                "count": len(dated),
            }
        )
    return result


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["date", *[label for label, _ in MATURITIES]])
        for row in rows:
            writer.writerow(
                [
                    row["date"],
                    *["" if value is None else f"{value:.2f}" for value in row["rates"]],
                ]
            )
    return path


def js_json(value):
    return json.dumps(value, separators=(",", ":"))


def write_html(rows, output_dir):
    labels = [label for label, _ in MATURITIES]
    page_title = "US Treasury Yield Curve History"
    page_description = (
        "Interactive daily U.S. Treasury yield curve chart with historical par yield curve rates "
        "from 1990 to the latest available Treasury data."
    )
    page_keywords = (
        "US Treasury yield curve, Treasury rates, yield curve history, Treasury par yield curve, "
        "interest rates, bond yields, 10 year Treasury, 2 year Treasury, 3 month Treasury"
    )
    canonical_url = "https://fujiapple852.github.io/yield/"
    preview_image_url = f"{canonical_url}assets/screenshot.png"
    repo_url = "https://github.com/fujiapple852/yield"
    analytics_pixel_url = "https://cloud.umami.is/p/aBmsBOhEl"
    meta = {
        "source": "U.S. Department of the Treasury Daily Treasury Par Yield Curve Rates",
        "sourceUrl": DATA_URL.format(year=date.today().year),
        "generatedOn": date.today().isoformat(),
        "firstDate": rows[0]["date"],
        "lastDate": rows[-1]["date"],
        "rowCount": len(rows),
        "maturities": labels,
        "domain": y_domain(rows),
        "coverage": coverage(rows),
    }
    dates = [row["date"] for row in rows]
    rates = [row["rates"] for row in rows]
    coverage_text = "; ".join(
        f"{item['label']} {item['first']} to {item['last']}" for item in meta["coverage"] if item["first"]
    )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <meta name="description" content="{html.escape(page_description)}">
  <meta name="keywords" content="{html.escape(page_keywords)}">
  <meta name="author" content="FujiApple">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#249af3">
  <meta name="apple-mobile-web-app-title" content="Yield Curve">
  <link rel="canonical" href="{html.escape(canonical_url)}">
  <link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="assets/favicon-32x32.png" sizes="32x32" type="image/png">
  <link rel="icon" href="assets/favicon-16x16.png" sizes="16x16" type="image/png">
  <link rel="apple-touch-icon" href="assets/apple-touch-icon.png" sizes="180x180">
  <link rel="manifest" href="assets/site.webmanifest">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{html.escape(page_title)}">
  <meta property="og:description" content="{html.escape(page_description)}">
  <meta property="og:url" content="{html.escape(canonical_url)}">
  <meta property="og:image" content="{html.escape(preview_image_url)}">
  <meta property="og:site_name" content="US Treasury Yield Curve">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{html.escape(page_title)}">
  <meta name="twitter:description" content="{html.escape(page_description)}">
  <meta name="twitter:image" content="{html.escape(preview_image_url)}">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --ink: #20242a;
      --muted: #5f6875;
      --line: #d7dce3;
      --line-strong: #b9c2cd;
      --accent: #249af3;
      --accent-dark: #1175c6;
      --panel: #ffffff;
      --soft: #eef6fd;
      --positive: #1f8f55;
      --negative: #b94747;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
    }}

    .analytics-pixel {{
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }}

    .app {{
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto auto 1fr;
    }}

    header {{
      padding: 18px clamp(16px, 3vw, 36px) 12px;
      background: #fff;
      border-bottom: 1px solid var(--line);
    }}

    .topline {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }}

    h1 {{
      margin: 0;
      font-size: clamp(1.35rem, 2vw, 2rem);
      font-weight: 720;
      letter-spacing: 0;
    }}

    .source {{
      color: var(--muted);
      font-size: 0.88rem;
    }}

    .source a {{ color: var(--accent-dark); text-decoration: none; }}
    .source a:hover {{ text-decoration: underline; }}

    .header-actions {{
      display: inline-flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}

    .repo-link {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      min-height: 34px;
      padding: 0 12px;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font-size: 0.88rem;
      font-weight: 650;
      text-decoration: none;
      box-shadow: 0 1px 2px rgba(32, 36, 42, 0.05);
    }}

    .repo-link:hover {{
      border-color: var(--accent);
      color: var(--accent-dark);
      background: #f9fcff;
    }}

    .repo-link svg {{
      width: 16px;
      height: 16px;
      flex: 0 0 auto;
    }}

    .stats {{
      margin-top: 12px;
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 10px;
    }}

    .stat {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      background: #fbfcfd;
      min-height: 62px;
    }}

    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}

    .stat strong {{
      display: block;
      margin-top: 4px;
      font-size: 1.05rem;
      font-weight: 700;
      word-break: break-word;
    }}

    .controls {{
      display: grid;
      grid-template-columns: auto minmax(200px, 1fr) auto auto auto auto;
      gap: 12px;
      align-items: center;
      padding: 12px clamp(16px, 3vw, 36px);
      background: #fff;
      border-bottom: 1px solid var(--line);
    }}

    button, select, input[type="date"] {{
      min-height: 38px;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}

    button {{
      width: 42px;
      display: inline-grid;
      place-items: center;
      cursor: pointer;
    }}

    button:hover {{ border-color: var(--accent); color: var(--accent-dark); }}

    select, input[type="date"] {{
      padding: 0 10px;
    }}

    .toggle {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      color: var(--muted);
      font-size: 0.9rem;
      white-space: nowrap;
    }}

    .toggle input {{ width: 18px; height: 18px; accent-color: var(--accent); }}

    input[type="range"] {{
      width: 100%;
      accent-color: var(--accent);
    }}

    main {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 260px;
      gap: 14px;
      padding: 14px clamp(16px, 3vw, 36px) 22px;
    }}

    .chart-wrap {{
      position: relative;
      min-height: min(68vh, 720px);
      height: calc(100vh - 245px);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}

    canvas {{
      width: 100%;
      height: 100%;
      display: block;
    }}

    .hovercard {{
      position: absolute;
      pointer-events: none;
      transform: translate(-50%, calc(-100% - 12px));
      background: rgba(32, 36, 42, 0.92);
      color: #fff;
      border-radius: 8px;
      padding: 7px 9px;
      font-size: 0.82rem;
      white-space: nowrap;
      opacity: 0;
      transition: opacity 120ms ease;
    }}

    aside {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
    }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }}

    .panel h2 {{
      margin: 0 0 10px;
      font-size: 0.92rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-weight: 700;
    }}

    .values {{
      display: grid;
      gap: 6px;
    }}

    .value-row {{
      display: grid;
      grid-template-columns: 46px 1fr auto;
      gap: 8px;
      align-items: center;
      min-height: 22px;
      font-size: 0.9rem;
    }}

    .bar {{
      height: 6px;
      border-radius: 999px;
      background: var(--soft);
      overflow: hidden;
    }}

    .bar i {{
      display: block;
      height: 100%;
      width: 0%;
      background: var(--accent);
      border-radius: 999px;
    }}

    .metrics {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}

    .metric {{
      padding: 9px;
      border-radius: 8px;
      background: #f7f9fb;
      border: 1px solid var(--line);
    }}

    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 0.76rem;
    }}

    .metric strong {{
      display: block;
      margin-top: 3px;
      font-size: 1rem;
    }}

    .note {{
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.4;
    }}

    @media (max-width: 900px) {{
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .controls {{ grid-template-columns: auto minmax(0, 1fr) auto; }}
      .controls select, .controls input[type="date"], .toggle {{ grid-column: span 1; }}
      main {{ grid-template-columns: 1fr; }}
      .chart-wrap {{ height: 58vh; min-height: 420px; }}
      aside {{ display: grid; grid-template-columns: 1fr 1fr; }}
    }}

    @media (max-width: 620px) {{
      header {{ padding-top: 14px; }}
      .stats {{ grid-template-columns: 1fr; }}
      .controls {{
        grid-template-columns: auto 1fr;
        gap: 10px;
      }}
      .controls select, .controls input[type="date"], .toggle {{
        grid-column: span 2;
        width: 100%;
      }}
      main {{ padding-inline: 10px; }}
      .chart-wrap {{ min-height: 360px; }}
      aside {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <img class="analytics-pixel" src="{html.escape(analytics_pixel_url)}" alt="" width="1" height="1" aria-hidden="true">
  <div class="app">
    <header>
      <div class="topline">
        <h1>US Treasury Yield Curve</h1>
        <div class="header-actions">
          <div class="source">Data: <a href="{html.escape(meta['sourceUrl'])}">U.S. Treasury</a></div>
          <a class="repo-link" href="{html.escape(repo_url)}" target="_blank" rel="noopener noreferrer" aria-label="Open GitHub repository">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7"/><path d="M7 7h10v10"/></svg>
            GitHub
          </a>
        </div>
      </div>
      <div class="stats">
        <div class="stat"><span>Selected date</span><strong id="dateLabel"></strong></div>
        <div class="stat"><span>History</span><strong>{html.escape(meta['firstDate'])} to {html.escape(meta['lastDate'])}</strong></div>
        <div class="stat"><span>Observations</span><strong>{meta['rowCount']:,} market days</strong></div>
        <div class="stat"><span>Maturities</span><strong>1M to 30Y</strong></div>
      </div>
    </header>

    <section class="controls" aria-label="Animation controls">
      <button id="play" aria-label="Play or pause" title="Play or pause">
        <svg id="playIcon" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
      </button>
      <input id="slider" type="range" min="0" max="{len(rows) - 1}" value="{len(rows) - 1}" aria-label="Timeline">
      <input id="datePicker" type="date" min="{html.escape(meta['firstDate'])}" max="{html.escape(meta['lastDate'])}" value="{html.escape(meta['lastDate'])}" aria-label="Date">
      <select id="speed" aria-label="Playback speed">
        <option value="80">Fast</option>
        <option value="160" selected>Medium</option>
        <option value="320">Slow</option>
      </select>
      <label class="toggle"><input id="autoScale" type="checkbox" checked> Auto scale</label>
      <button id="download" aria-label="Download CSV" title="Download CSV">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>
      </button>
    </section>

    <main>
      <section class="chart-wrap">
        <canvas id="chart"></canvas>
        <div id="hovercard" class="hovercard"></div>
      </section>
      <aside>
        <section class="panel">
          <h2>Curve Values</h2>
          <div id="values" class="values"></div>
        </section>
        <section class="panel">
          <h2>Shape</h2>
          <div class="metrics">
            <div class="metric"><span>2s10s slope</span><strong id="spread2s10s"></strong></div>
            <div class="metric"><span>3m10y slope</span><strong id="spread3m10y"></strong></div>
            <div class="metric"><span>Low</span><strong id="lowValue"></strong></div>
            <div class="metric"><span>High</span><strong id="highValue"></strong></div>
          </div>
        </section>
        <section class="panel">
          <h2>Coverage</h2>
          <div class="note">Missing values indicate that the selected tenor is blank or unavailable in the Treasury yield curve feed for that date.</div>
        </section>
      </aside>
    </main>
  </div>

  <script>
    const META = {js_json(meta)};
    const DATES = {js_json(dates)};
    const RATES = {js_json(rates)};
    const LABELS = META.maturities;
    const GLOBAL_DOMAIN = META.domain;
    const X_POS = LABELS.map((_, i) => i);

    const canvas = document.getElementById('chart');
    const ctx = canvas.getContext('2d');
    const hovercard = document.getElementById('hovercard');
    const slider = document.getElementById('slider');
    const playButton = document.getElementById('play');
    const playIcon = document.getElementById('playIcon');
    const datePicker = document.getElementById('datePicker');
    const speed = document.getElementById('speed');
    const autoScale = document.getElementById('autoScale');
    const dateLabel = document.getElementById('dateLabel');
    const valuesEl = document.getElementById('values');
    const spread2s10s = document.getElementById('spread2s10s');
    const spread3m10y = document.getElementById('spread3m10y');
    const lowValue = document.getElementById('lowValue');
    const highValue = document.getElementById('highValue');
    const downloadButton = document.getElementById('download');

    let index = DATES.length - 1;
    let timer = null;
    let hover = null;
    let pointCache = [];

    function fmt(value) {{
      return value == null ? 'n/a' : value.toFixed(2) + '%';
    }}

    function fmtSpread(value) {{
      if (value == null) return 'n/a';
      const bps = Math.round(value * 100);
      const sign = bps > 0 ? '+' : '';
      return sign + bps + ' bps';
    }}

    function localDate(dateText) {{
      const [y, m, d] = dateText.split('-').map(Number);
      return new Date(y, m - 1, d).toLocaleDateString(undefined, {{
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      }});
    }}

    function resizeCanvas() {{
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    }}

    function getDomain(row) {{
      if (!autoScale.checked) return GLOBAL_DOMAIN;
      const values = row.filter(v => v != null);
      let low = Math.min(...values);
      let high = Math.max(...values);
      if (high - low < 0.8) {{
        const pad = (0.8 - (high - low)) / 2;
        low -= pad;
        high += pad;
      }}
      low = Math.floor((low - 0.08) * 10) / 10;
      high = Math.ceil((high + 0.08) * 10) / 10;
      return [low, high];
    }}

    function makeScale(width, height, domain) {{
      const margin = {{
        top: 34,
        right: width < 640 ? 18 : 34,
        bottom: width < 640 ? 48 : 58,
        left: width < 640 ? 44 : 58
      }};
      const innerW = width - margin.left - margin.right;
      const innerH = height - margin.top - margin.bottom;
      const x = i => margin.left + (i / (LABELS.length - 1)) * innerW;
      const y = v => margin.top + ((domain[1] - v) / (domain[1] - domain[0])) * innerH;
      return {{ margin, innerW, innerH, x, y }};
    }}

    function drawGrid(width, height, scale, domain) {{
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);

      const ticks = 6;
      ctx.lineWidth = 1;
      ctx.font = '13px Inter, system-ui, sans-serif';
      ctx.textBaseline = 'middle';

      for (let t = 0; t <= ticks; t++) {{
        const value = domain[0] + (domain[1] - domain[0]) * (t / ticks);
        const y = scale.y(value);
        ctx.strokeStyle = '#e1e5ea';
        ctx.beginPath();
        ctx.moveTo(scale.margin.left, y);
        ctx.lineTo(width - scale.margin.right, y);
        ctx.stroke();
        ctx.fillStyle = '#515966';
        ctx.textAlign = 'right';
        ctx.fillText(value.toFixed(1), scale.margin.left - 10, y);
      }}

      LABELS.forEach((label, i) => {{
        const x = scale.x(i);
        ctx.strokeStyle = '#e5e8ec';
        ctx.beginPath();
        ctx.moveTo(x, scale.margin.top);
        ctx.lineTo(x, height - scale.margin.bottom);
        ctx.stroke();
        ctx.fillStyle = '#20242a';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(label, x, height - scale.margin.bottom + 14);
      }});

      ctx.strokeStyle = '#c7cdd5';
      ctx.lineWidth = 1.2;
      ctx.strokeRect(scale.margin.left, scale.margin.top, scale.innerW, scale.innerH);

      ctx.fillStyle = '#5f6875';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.font = '12px Inter, system-ui, sans-serif';
      ctx.fillText('Yield (%)', scale.margin.left, 11);
    }}

    function drawSmoothLine(points) {{
      if (points.length < 2) return;
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      for (let i = 0; i < points.length - 1; i++) {{
        const p0 = points[Math.max(0, i - 1)];
        const p1 = points[i];
        const p2 = points[i + 1];
        const p3 = points[Math.min(points.length - 1, i + 2)];
        const cp1x = p1.x + (p2.x - p0.x) / 6;
        const cp1y = p1.y + (p2.y - p0.y) / 6;
        const cp2x = p2.x - (p3.x - p1.x) / 6;
        const cp2y = p2.y - (p3.y - p1.y) / 6;
        ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
      }}
      ctx.stroke();
    }}

    function draw() {{
      const rect = canvas.getBoundingClientRect();
      const width = rect.width;
      const height = rect.height;
      const row = RATES[index];
      const domain = getDomain(row);
      const scale = makeScale(width, height, domain);

      drawGrid(width, height, scale, domain);

      pointCache = row
        .map((value, i) => value == null ? null : {{
          label: LABELS[i],
          value,
          x: scale.x(i),
          y: scale.y(value)
        }})
        .filter(Boolean);

      ctx.save();
      ctx.shadowColor = 'rgba(36, 154, 243, 0.18)';
      ctx.shadowBlur = 10;
      ctx.strokeStyle = '#249af3';
      ctx.lineWidth = 4;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      drawSmoothLine(pointCache);
      ctx.restore();

      for (const point of pointCache) {{
        ctx.fillStyle = '#249af3';
        ctx.beginPath();
        ctx.arc(point.x, point.y, 5.1, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }}

      if (hover) {{
        const p = pointCache[hover];
        if (p) {{
          ctx.strokeStyle = 'rgba(17, 117, 198, 0.32)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(p.x, scale.margin.top);
          ctx.lineTo(p.x, height - scale.margin.bottom);
          ctx.stroke();
          ctx.fillStyle = '#1175c6';
          ctx.beginPath();
          ctx.arc(p.x, p.y, 7.3, 0, Math.PI * 2);
          ctx.fill();
          hovercard.style.left = p.x + 'px';
          hovercard.style.top = p.y + 'px';
          hovercard.textContent = `${{p.label}}  ${{fmt(p.value)}}`;
          hovercard.style.opacity = 1;
        }}
      }} else {{
        hovercard.style.opacity = 0;
      }}
    }}

    function updatePanels() {{
      const date = DATES[index];
      const row = RATES[index];
      slider.value = index;
      datePicker.value = date;
      dateLabel.textContent = localDate(date);

      const values = row.filter(v => v != null);
      const low = Math.min(...values);
      const high = Math.max(...values);
      const range = Math.max(0.01, high - low);

      valuesEl.innerHTML = row.map((value, i) => {{
        const width = value == null ? 0 : ((value - low) / range) * 100;
        return `<div class="value-row"><strong>${{LABELS[i]}}</strong><div class="bar"><i style="width:${{width}}%"></i></div><span>${{fmt(value)}}</span></div>`;
      }}).join('');

      const twoY = row[LABELS.indexOf('2Y')];
      const tenY = row[LABELS.indexOf('10Y')];
      const threeM = row[LABELS.indexOf('3M')];
      spread2s10s.textContent = twoY == null || tenY == null ? 'n/a' : fmtSpread(tenY - twoY);
      spread3m10y.textContent = threeM == null || tenY == null ? 'n/a' : fmtSpread(tenY - threeM);
      lowValue.textContent = fmt(low);
      highValue.textContent = fmt(high);

      draw();
    }}

    function setIndex(next) {{
      index = Math.max(0, Math.min(DATES.length - 1, next));
      updatePanels();
    }}

    function nearestDateIndex(dateText) {{
      let lo = 0;
      let hi = DATES.length - 1;
      while (lo < hi) {{
        const mid = Math.floor((lo + hi) / 2);
        if (DATES[mid] < dateText) lo = mid + 1;
        else hi = mid;
      }}
      if (lo > 0) {{
        const before = new Date(DATES[lo - 1]).getTime();
        const after = new Date(DATES[lo]).getTime();
        const target = new Date(dateText).getTime();
        return target - before <= after - target ? lo - 1 : lo;
      }}
      return lo;
    }}

    function setPlaying(playing) {{
      if (timer) {{
        clearInterval(timer);
        timer = null;
      }}
      if (playing) {{
        timer = setInterval(() => {{
          setIndex(index >= DATES.length - 1 ? 0 : index + 1);
        }}, Number(speed.value));
        playIcon.innerHTML = '<path d="M7 5h4v14H7zM13 5h4v14h-4z"/>';
      }} else {{
        playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
      }}
    }}

    canvas.addEventListener('mousemove', event => {{
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      let nearest = null;
      let distance = Infinity;
      pointCache.forEach((point, i) => {{
        const d = Math.hypot(point.x - x, point.y - y);
        if (d < distance) {{
          distance = d;
          nearest = i;
        }}
      }});
      hover = distance < 24 ? nearest : null;
      draw();
    }});

    canvas.addEventListener('mouseleave', () => {{
      hover = null;
      draw();
    }});

    slider.addEventListener('input', () => setIndex(Number(slider.value)));
    datePicker.addEventListener('change', () => setIndex(nearestDateIndex(datePicker.value)));
    playButton.addEventListener('click', () => setPlaying(!timer));
    speed.addEventListener('change', () => {{
      if (timer) setPlaying(true);
    }});
    autoScale.addEventListener('change', draw);

    downloadButton.addEventListener('click', () => {{
      const header = ['date', ...LABELS].join(',');
      const lines = RATES.map((row, i) => [DATES[i], ...row.map(v => v == null ? '' : v.toFixed(2))].join(','));
      const blob = new Blob([[header, ...lines].join('\\n')], {{ type: 'text/csv' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'us_treasury_yield_curve_history.csv';
      a.click();
      URL.revokeObjectURL(url);
    }});

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();
    updatePanels();
  </script>
</body>
</html>
"""
    path = output_dir / "index.html"
    path.write_text(document, encoding="utf-8")
    return path


def copy_assets(output_dir):
    source = DEFAULT_ASSETS_DIR
    if not source.exists():
        return []
    target = output_dir / "assets"
    if source.resolve() == target.resolve():
        return sorted(path for path in source.iterdir() if path.is_file())
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in source.iterdir():
        if path.is_file():
            destination = target / path.name
            shutil.copy2(path, destination)
            copied.append(destination)
    return copied


def main():
    parser = argparse.ArgumentParser(description="Build the static US Treasury yield curve site.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write the static site files. Defaults to ./public.",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=DEFAULT_DATA_FILE,
        help="CSV history file to update incrementally. Defaults to ./data/us_treasury_yield_curve_history.csv.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=1990,
        help="First Treasury data year to fetch when no history exists or --full-refresh is set.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Last Treasury data year to fetch. Defaults to the current year.",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Ignore existing CSV history and fetch all years from --start-year.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    data_file = args.data_file.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_rows = [] if args.full_refresh else read_csv(data_file)
    if existing_rows:
        last_year = int(existing_rows[-1]["date"][:4])
        fetch_start_year = max(args.start_year, last_year)
    else:
        fetch_start_year = args.start_year
    fetched_rows = fetch_years(start_year=fetch_start_year, end_year=args.end_year)
    rows = merge_rows(existing_rows, fetched_rows)
    if not rows:
        raise SystemExit("No data fetched.")
    data_path = write_csv(rows, data_file)
    html_path = write_html(rows, output_dir)
    csv_path = write_csv(rows, output_dir / "us_treasury_yield_curve_history.csv")
    copied_assets = copy_assets(output_dir)
    print(f"Fetched years: {fetch_start_year} to {args.end_year or date.today().year}")
    print(f"Wrote {data_path}")
    print(f"Wrote {html_path}")
    print(f"Wrote {csv_path}")
    for asset_path in copied_assets:
        print(f"Wrote {asset_path}")
    print(f"Rows: {len(rows)} from {rows[0]['date']} to {rows[-1]['date']}")


if __name__ == "__main__":
    main()
