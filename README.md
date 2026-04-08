# Historical Analysis of Software Metrics

A Python package containing utilities to aid in the automated analysis of a PyPI packages software metrics over its lifespan.

This project was made to analyze the [collective/icalendar](https://github.com/collective/icalendar) project, though it can be adapted to any PyPI published package.

Results of the `collective/icalendar` analysis can be found in [graphs/](graphs/)

## Usage instructions

1. `download-versions.py`
    - Optionally, you may `git clone <target> versions/latest` to add the latest git-release as `vlatest`.
2. `generate-deps.py`
3. `generate-ck-metrics.py`
4. `generate-lcom-metrics.py`
5. `generate-sm-metrics.py`
6. `create-graphs.py`

