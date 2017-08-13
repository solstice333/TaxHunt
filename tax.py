from argparse import ArgumentParser
from xml.parsers.expat import ExpatError
from html.parser import HTMLParser
from xml.dom.minidom import Node

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
   @staticmethod
   def _get_text_from_cell(node):
      s = ''
      for n in node.childNodes:
         if (n.nodeType == Node.TEXT_NODE):
            s += n.nodeValue
         else:
            s += TaxTable._get_text_from_cell(n)
      return s

   def _is_single_tax_column(self):
      return self.columns >= 4 and \
         re.search(r'single', ''.join(self.headers), re.I)

   def _is_single_tax_table(self):
      return self.columns < 4 and \
         not re.search(r'single', ''.join(self.headers), re.I)

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

   @staticmethod
   def _get_aggregated_base_below(data, bkt_idx):
      return sum([bkt[3] for bkt in data[0:bkt_idx]])


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
      data = []
      if self.is_taxable_income_related():
         if self._is_single_tax_column():
            for data_row in self.data:
               data.append(
                  [self._parse_table_rate(data_row, 'rate'),
                  self._parse_table_min(data_row, 'single', 'filers'),
                  self._parse_table_max(data_row, 'single', 'filers')])
         elif self._is_single_tax_table(): 
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
      return data


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


class Taxable:
   def __init__(self, incomes):
      self._income = income   

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
   parser = ArgumentParser(description='a tool to help calculate taxes')
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

   req = TaxRequest(args.year)
   print("incomes: {}".format(args.INCOMES))
   if args.married:
      print('married')
      raise RuntimeError('NotYetImplemented')
   else:
      print(req.taxable_income_tables[0].data_single_tax)

   return req

if __name__ == '__main__':
   main()
