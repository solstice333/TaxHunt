# TaxHunt

## Description:

Simple command line utility to scrape tax data and do calculations with it

## Usage:

```
usage: taxhunt.py [-h] -y { 2014 to 2017 inclusive } [-m]
                  INCOMES [INCOMES ...]

a tool to help calculate taxes by scraping data from taxfoundation.org

Examples:
   python taxhunt.py -y 2017 64e3 120e3
   python taxhunt.py -y 2017 -m 225e3

positional arguments:
  INCOMES               list of incomes. Scientific notation, for instance,
                        10e3 is allowed

optional arguments:
  -h, --help            show this help message and exit
  -y { 2014 to 2017 inclusive }, --year { 2014 to 2017 inclusive }
                        the taxable year
  -m, --married
```
