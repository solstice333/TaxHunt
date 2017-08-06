import math
import urllib.request
from html.parser import HTMLParser

class TaxParser(HTMLParser):
   def __init__(self, start_func, end_func, data_func):
      self._start = start_func   
      self._end = end_func
      self._data = data_func
      self._path = []
      super().__init__()

   def handle_starttag(self, tag, attrs):
      self._start(tag, attrs)

   def handle_endtag(self, tag):
      self._end(tag)

   def handle_data(self, data):
      self._data(data)

class TaxRequest:
   @staticmethod
   def _handle_starttag(tag, attrs):
      print("start tag and attrs: {} {}".format(tag, attrs))

   @staticmethod
   def _handle_endtag(tag):
      print("end tag: {}".format(tag))

   @staticmethod
   def _handle_data(data):
      print("data: {}".format(data))

   def __init__(self, yr):
      self._url = "https://taxfoundation.org/{}-tax-brackets/".format(yr)
      with urllib.request.urlopen(self._url) as data:
         self._content = data.read().decode()
      self._tax_parser = TaxParser(
         TaxRequest._handle_starttag,
         TaxRequest._handle_endtag,
         TaxRequest._handle_data )

   @property
   def content(self):
      return self._content

   def querySelectorAll(self, selector):
      self._tax_parser.feed(self.content)

class Taxable:
   def __init__(self, incomes):
      self._income = income   

if __name__ == '__main__':
   req = TaxRequest(2017)
   print(req.querySelectorAll('table'))





