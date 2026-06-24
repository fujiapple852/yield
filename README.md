# US Treasury Yield Curve

Static GitHub Pages site for an animated US Treasury yield curve history.

[![Live site](https://img.shields.io/badge/Live%20site-GitHub%20Pages-2ea44f?style=for-the-badge)](https://fujiapple852.github.io/yield/)

![Screenshot of the US Treasury Yield Curve site](assets/screenshot.png)

## Build locally

```sh
python3 scripts/build_yield_curve_site.py --output-dir public
```

The build pulls daily Treasury par yield curve XML data from 1990 through the current year and the PCE price index from FRED, then writes:

- `data/us_treasury_yield_curve_history.csv`
- `data/us_pce_price_index.csv`
- `public/index.html`
- `public/us_treasury_yield_curve_history.csv`
- `public/us_pce_price_index.csv`

The CSV files under `data/` are the persisted histories. Normal builds read them first, fetch only recent source data, then merge rows by date. Use `--full-refresh` to rebuild the complete histories from the source feeds.

## Deploy

GitHub Actions runs `.github/workflows/deploy-pages.yml` on weekdays at 23:05 UTC and on manual dispatch. Treasury says yield curve rates are usually available by 6:00 PM Eastern Time each trading day; that is 22:00 UTC during daylight saving time and 23:00 UTC during standard time, so this schedule runs shortly after the publication window year-round. The workflow fetches the latest site data incrementally, commits changed CSV files under `data/`, builds the static site into `public/`, uploads the Pages artifact, and deploys it with GitHub Pages.

In the repository settings, set Pages to use **GitHub Actions** as the source.

## License

The project code and non-data site/documentation assets are released under the [MIT License](LICENSE).

The source data and normalized CSV histories are not covered by the MIT License. See [DATA_LICENSE.md](DATA_LICENSE.md) for the data notice.

## Data

Yield curve data comes from the U.S. Department of the Treasury's [Daily Treasury Par Yield Curve Rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve) and XML feed.

The original Treasury data is a work of the United States Government. Under [17 U.S.C. § 105](https://www.law.cornell.edu/uscode/text/17/105), copyright protection is not available for works of the United States Government. This project does not claim copyright over the original Treasury data and is not affiliated with or endorsed by the U.S. Department of the Treasury.

PCE price index data comes from the Federal Reserve Bank of St. Louis FRED series [Personal Consumption Expenditures: Chain-type Price Index (PCEPI)](https://fred.stlouisfed.org/series/PCEPI), sourced from the U.S. Bureau of Economic Analysis.
