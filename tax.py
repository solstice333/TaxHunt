import math
import re
import urllib.request
import xml.dom.minidom
import xml.dom
import html.entities
from xml.parsers.expat import ExpatError
from html.parser import HTMLParser
from xml.dom.minidom import Node

class TableParser(HTMLParser):
   xhtml = { v: "&{};".format(k) 
      for k, v in html.entities.html5.items()
      if k in ['quot', 'amp', 'apos', 'lt', 'gt']}

   @staticmethod
   def _to_entity(match_obj):
      m = match_obj.group(0)
      if TableParser.xhtml.get(m):
         return "{}".format(TableParser.xhtml[m])
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

   def __init__(self, table_elem):
      self._table = table_elem

   @property
   def columns(self):
      return len(self._table.getElementsByTagName('th'))

   @property
   def data(self):
      datalist = [] 
      data = []
      cols = self.columns
      idx = 0

      datalist.append(tuple([TaxTable._get_text_from_cell(n) 
         for n in self._table.getElementsByTagName('th')]))

      tds = self._table.\
         getElementsByTagName('tbody')[0].getElementsByTagName('td')
      for n in tds: 
         data.append(TaxTable._get_text_from_cell(n)) 
         idx += 1
         if idx % cols == 0:
            datalist.append(tuple(data))
            data.clear()

      return datalist

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

class Taxable:
   def __init__(self, incomes):
      self._income = income   

def main():
   req = TaxRequest(2017)
   return req.tables

if __name__ == '__main__':
   main()
