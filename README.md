# Warsaw Parties Dashboard

Interactive dashboard of electronic music events in Warsaw, sourced from Resident Advisor (ra.co).

**Live site:** https://YOUR_USERNAME.github.io/warsaw-ra-dashboard

## Features

- Date range slider filtering all charts and the event table
- Events per month bar chart
- Attendance per month bar chart
- Top venues horizontal bar chart (with address tooltip)
- Searchable, sortable event table with links to RA

## Data

`data.json` — 7,482 events scraped from the RA GraphQL API, covering Oct 2003 – Mar 2026.

Each event includes: title, date, start/end time, venue (name + address), artists, attending count, ticket cost, and RA URL.

## Hosting on GitHub Pages

1. Create a new repo on GitHub named `warsaw-ra-dashboard`
2. Push this repo:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/warsaw-ra-dashboard.git
   git push -u origin main
   ```
3. Go to **Settings → Pages**, set source to **Deploy from branch → main → / (root)**
4. Your dashboard will be live at `https://YOUR_USERNAME.github.io/warsaw-ra-dashboard`
