from argparse import ArgumentParser, RawDescriptionHelpFormatter
from xml.parsers.expat import ExpatError
from html.parser import HTMLParser
from xml.dom.minidom import Node
from collections import namedtuple
from enum import Enum

import argparse
import math
import re
import urllib.request
import xml.dom.minidom
import xml.dom
import html.entities
import time


class NotTaxableIncomeRelatedError(Exception):
   def __init__(self):
      super().__init__()


class FilerType(Enum):
   SINGLE = 'single'
   MARRIED = 'married'


class TableParser(HTMLParser):
   entitydefs = { v: "&{};".format(k) 
      for k, v in html.entities.entitydefs.items()
      if k in html.entities.entitydefs and k in html.entities.html5 }

   @staticmethod
   def _to_entity(match_obj):
      m = match_obj.group(0)
      try:
         return "{}".format(TableParser.entitydefs[m])
      except KeyError:
         return m

   def __init__(self, *args, **kwargs):
      self._capture = False
      self._data = ''
      super().__init__(*args, **kwargs)   

   def handle_starttag(self, tag, attrs):
      if (tag == 'table'):
         self._capture = True

      if self._capture:
         self._data += "<{}".format(tag)
         if attrs:
            for a in attrs:
               self._data += " {}=\"{}\"".format(*a)
         self._data += ">"

   def handle_endtag(self, tag):
      if (self._capture):
         self._data += "</{}>".format(tag)

      if (tag == 'table'):
         self._capture = False

   def handle_data(self, data):
      if self._capture:
         data = data.strip()
         if data:
            data = re.sub(r'\S', TableParser._to_entity, data)
            self._data += "{}".format(data)

   def feed(self, data):
      super().feed(data)
      self._data = "<?xml version=\"1.0\" encoding=\"utf-8\"?>" + \
         "<!DOCTYPE html>" + \
         "<html><body>" + self._data + "</body></html>"
      return self._data


class TaxTable:
   _Bracket = namedtuple('Bracket', ['rate', 'min', 'max', 'max_owe'])
   _FilerMethod = namedtuple('FilerMethod', ['has_col', 'is_table'])

   @staticmethod
   def _get_text_from_cell(node):
      s = ''
      for n in node.childNodes:
         if (n.nodeType == Node.TEXT_NODE):
            s += n.nodeValue
         else:
            s += TaxTable._get_text_from_cell(n)
      return s

   @staticmethod
   def _get_aggregated_base_below(data, bkt_idx):
      return sum([bkt[3] for bkt in data[0:bkt_idx]])

   def _has_tax_column(self, filertype):
      return self.columns >= 4 and \
         re.search(re.escape(filertype.value), ''.join(self.headers), re.I)

   def _is_tax_table(self, filertype):
      return self.columns < 4 and \
         not re.search(re.escape(filertype.value), 
            ''.join(self.headers), re.I) and \
         re.search(re.escape(filertype.value), self.title, re.I)

   def _has_single_tax_column(self):
      return self._has_tax_column(FilerType.SINGLE)

   def _is_single_tax_table(self):
      return self._is_tax_table(FilerType.SINGLE)

   def _has_married_tax_column(self):
      return self._has_tax_column(FilerType.MARRIED)

   def _is_married_tax_table(self):
      return self._is_tax_table(FilerType.MARRIED)

   def _idx_search(self, *terms):
      idx = 0

      for hdr in self.headers:
         next_header = False

         for term in terms:
            if not re.search(re.escape(term), hdr, re.I):
               next_header = True
               break 

         if next_header:
            idx += 1
            continue

         return idx

   def _parse_table_rate(self, data_row, *terms):
      rate_idx = self._idx_search(*terms)
      rate = re.search(r'(\d+(\.\d+)?)%', data_row[rate_idx])
      return float(rate.group(1))/100

   def _parse_table_min(self, data_row, *terms):
      bkt_idx = self._idx_search(*terms)
      bkt = data_row[bkt_idx].replace(',', '')
      bkt = re.search(r'\$(\d+(\.\d+)?)', bkt)
      return float(bkt.group(1))

   def _parse_table_max(self, data_row, *terms):
      bkt_idx = self._idx_search(*terms)
      bkt = data_row[bkt_idx].replace(',', '')
      bkt = re.search(r'to \$?(\d+(\.\d+)?)', bkt)
      return float(bkt.group(1)) if bkt else None

   def _add_max_base(self, data):
      for bkt in data:
         if (bkt[2] is None):
            bkt.append(None)
         else:
            bkt.append(bkt[0]*(bkt[2] - bkt[1]))
      return data

   @property
   def _col_table_meths(self):
      return {
         FilerType.SINGLE: 
            TaxTable._FilerMethod(
               self._has_single_tax_column, self._is_single_tax_table),
         FilerType.MARRIED: 
            TaxTable._FilerMethod(
               self._has_married_tax_column, self._is_married_tax_table) }

   def __init__(self, table_elem):
      self._table = table_elem

   @property
   def columns(self):
      return len(self._table.getElementsByTagName('th') or
         self._table.getElementsByTagName('tr')[0].getElementsByTagName('td'))

   @property
   def title(self):
      titles = self._table.getElementsByTagName('caption') or \
         self._table.getElementsByTagName('thead')
      return TaxTable._get_text_from_cell(titles[0])    

   @property
   def headers(self):
      headers = \
         self._table.getElementsByTagName('thead')[0].\
         getElementsByTagName('th')
      return tuple([TaxTable._get_text_from_cell(th) for th in headers])

   def is_taxable_income_related(self):
      return bool(re.search(r'taxable.*income', self.title, re.I)) or \
         bool(re.search('rates', self.title, re.I)) and \
         bool(re.search('brackets', self.title, re.I))

   @property
   def data(self):
      datalist = [] 
      data = []
      cols = self.columns
      idx = 0

      tds = self._table.\
         getElementsByTagName('tbody')[0].getElementsByTagName('td')
      for n in tds: 
         data.append(TaxTable._get_text_from_cell(n)) 
         idx += 1
         if idx % cols == 0:
            datalist.append(tuple(data))
            data.clear()

      return datalist

   @property
   def data_single_tax(self):
      return self.tax_data(FilerType.SINGLE)

   @property
   def data_married_tax(self):
      return self.tax_data(FilerType.MARRIED)

   def is_single_table(self):
      return self._is_single_tax_table() or self._has_single_tax_column()

   def is_married_table(self):
      return self._is_married_tax_table() or self._has_married_tax_column() 

   def tax_data(self, filer_type):
      data = []

      if self.is_taxable_income_related():
         if self._col_table_meths[filer_type].has_col():
            for data_row in self.data:
               data.append(
                  [self._parse_table_rate(data_row, 'rate'),
                  self._parse_table_min(data_row, filer_type.value, 'filers'),
                  self._parse_table_max(data_row, filer_type.value, 'filers')])
         elif self._col_table_meths[filer_type].is_table():
            for data_row in self.data:
               data.append(
                  [self._parse_table_rate(data_row, 'rate'),
                  self._parse_table_min(
                     data_row, 'taxable', 'income', 'bracket'),
                  self._parse_table_max(
                     data_row, 'taxable', 'income', 'bracket')])
         data = self._add_max_base(data)
      else:
         raise NotTaxableIncomeRelatedError()

      return list(map(lambda d: TaxTable._Bracket(*d), data))


class TaxRequest:
   def __init__(self, yr):
      self._url = "https://taxfoundation.org/{}-tax-brackets/".format(yr)
      with urllib.request.urlopen(self._url) as data:
         content = data.read().decode()
      tax_tables = TableParser().feed(content)
      document = xml.dom.minidom.parseString(tax_tables)
      self._tables = document.getElementsByTagName('table')

   @property
   def tables(self):
      return [TaxTable(table) for table in self._tables]

   @property
   def taxable_income_tables(self):
      return [table for table in self.tables 
         if table.is_taxable_income_related()]

   @property
   def single_table(self):
      for table in self.taxable_income_tables:
         if table.is_single_table():
            return table

   @property
   def married_table(self):
      for table in self.taxable_income_tables:
         if table.is_married_table():
            return table


class Taxable:
   def __init__(self, year, married, incomes):
      self._incomes = incomes  
      self._year = year
      self._married = married

   @property
   def tax_owed(self):
      """return tax owed for all values in the incomes list

      >>> Taxable(2016, False, [49000]).tax_owed
      [8021.25]

      >>> Taxable(2016, True, [49000]).tax_owed
      [6422.5]

      >>> Taxable(2017, False, [49000]).tax_owed
      [7988.75]

      >>> Taxable(2017, True, [49000]).tax_owed
      [6417.5]
      """
      req = TaxRequest(self._year)
      tax_owed = []

      for income in self._incomes:
         if self._married:
            tax_data = \
               [bkt for bkt in req.married_table.data_married_tax
                  if income > bkt.min]
         else:
            tax_data = \
               [bkt for bkt in req.single_table.data_single_tax 
                  if income > bkt.min]

         owe = 0
         for bkt in tax_data:
            if income > bkt.max:
               owe += bkt.max_owe
            else:
               owe += (income - bkt.min)*bkt.rate
         tax_owed.append(owe)

      return tax_owed

   @property
   def year(self):
      return self._year

   @year.setter
   def year(self, yr):
      self._year = yr

   @property
   def incomes(self):
      return self._incomes

   @incomes.setter
   def incomes(self, incomes):
      self._incomes = incomes

   @property
   def married(self):
      return self._married

   @married.setter
   def married(self, married):
      self._married = married

   @property
   def single(self):
      return not self._married

   @single.setter
   def single(self, single):
      self._married = not single

def int_or_sci_notation(val):
   try:
      return int(val)
   except ValueError as ve:
      m = re.fullmatch(r'(\d+)e(\d+)$', val, re.I)
      if m:
         base = int(m.group(1))
         for i in range(0, int(m.group(2))):
            base *= 10
         return base
      raise ve

def main():
   parser = ArgumentParser(description="""\
a tool to help calculate taxes by scraping data from taxfoundation.org

Examples:
   python taxhunt.py -y 2017 64e3 120e3
   python taxhunt.py -y 2017 -m 225e3""",
      formatter_class=RawDescriptionHelpFormatter)
   parser.add_argument('-y', '--year', 
      required=True, 
      choices=range(2014, time.localtime().tm_year + 1), 
      type=int, 
      help='the taxable year',
      metavar="{{ 2014 to {} inclusive }}".format(time.localtime().tm_year))
   parser.add_argument('INCOMES', 
      type=int_or_sci_notation,
      nargs='+', 
      help='list of incomes. Scientific notation, ' +\
         'for instance, 10e3 is allowed')
   parser.add_argument('-m', '--married', action='store_true')
   args = parser.parse_args()

   taxable = Taxable(args.year, args.married, args.INCOMES)
   print(sum(taxable.tax_owed))

if __name__ == '__main__':
   main()
