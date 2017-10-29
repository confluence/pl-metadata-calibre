#!/usr/bin/env python2
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '(c) 2017 Adrianna Pińska <adrianna.pinska@gmail.com>'
__docformat__ = 'restructuredtext en'

import re
import datetime
import time

from Queue import Queue, Empty
from threading import Thread
from urllib import urlencode
from lxml.etree import fromstring, XMLParser

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from calibre.ebooks.chardet import xml_to_unicode
from calibre.utils.cleantext import clean_ascii_chars
from calibre.ebooks.metadata import check_isbn

class PWNObject(object):
    SEARCH_URL = 'https://ksiegarnia.pwn.pl/szukaj?%s'
    
    @classmethod
    def root_from_url(cls, browser, url, timeout, log):
        log.info('Fetching: %s' % url)
        response = browser.open_novisit(url, timeout=timeout)
        raw = response.read()
        parser = XMLParser(recover=True, no_network=True)
        return fromstring(xml_to_unicode(clean_ascii_chars(raw),
            strip_encoding_pats=True)[0], parser=parser)

    @classmethod
    def url_from_search(cls, params):
        return cls.SEARCH_URL % urlencode(params)


class SearchResults(PWNObject):
    @classmethod
    def url_from_isbn13(cls, isbn):
        return cls.url_from_search({"fa_ean": isbn})
    
    @classmethod
    def url_from_isbn10(cls, isbn):
        return cls.url_from_search({"faa_bookIdent": isbn})
    
    @classmethod
    def url_from_title_and_author(cls, title_tokens, author_tokens):
        title = ' '.join(title_tokens)
        author = ' '.join(author_tokens)
        return cls.url_from_search({"faa_name": title, "faa_creator": author})

    @classmethod
    def from_url(cls, browser, url, timeout, log):
        book_urls = []
        
        root = cls.root_from_url(browser, url, timeout, log)
        results = root.xpath('//div[@class="emp-info-container"]')
        
        base_url = 'https://ksiegarnia.pwn.pl'
        
        for result in results:
            url = base_url + result.xpath('a/@href')[0]
            book_urls.append(url)
        
        log.info("Parsed books from url %r. Found %d publications." % (url, len(book_urls)))
            
        return book_urls
    

class Book(PWNObject):
    @classmethod
    def from_url(cls, browser, url, timeout, log):
        properties = {}
        root = cls.root_from_url(browser, url, timeout, log)
        
        properties["rating"] = root.xpath('//span[@itemprop="rating"]/text()')[0]
        properties["title"] = root.xpath('//h1[@itemprop="name"]/span[@class="name"]/text()')[0]
        properties["cover_url"] = root.xpath('//div[@id="product-cover"]/div/a/@href')[0]
        
        details = root.xpath('//div[@class="emp-product-description"]/ul/li')
        
        for detail in details:
            try:
                section = detail.xpath('h3/span[@class="key"]/text()')[0]
            except IndexError:
                section = detail.xpath('h2/span[@class="key"]/text()')[0]
            
            if section == "Wydanie:":
                for value in detail.xpath('h3/span[@class="value"]/text()'):
                    if re.match('\d{4}', value):
                        properties["pubdate"] = datetime.datetime(year=int(value), month=1, day=1)
            elif section == "Autor:":
                # TODO better handling for multiple authors?
                properties["authors"] = detail.xpath('h2/span[@class="value"]/a/text()')
            elif section == "Wydawca:":
                properties["publisher"] = detail.xpath('h3/span[@class="value"]/a/text()')[0]
        
        details = root.xpath('//div[@id="details"]/ul[@class="head"]/li')
        
        for detail in details:
            section = detail.xpath('span[contains(@class, "text")]/text()')[0]
            if section == "ISBN:":
                properties["isbn"] = detail.xpath('span[@class="wartosc"]/text()')[0]
            elif section == "EAN:":
                properties["ean"] = detail.xpath('span[@class="wartosc"]/text()')[0]
            elif section == "Język wydania:":
                properties["languages"] = []
                language = detail.xpath('span[@class="wartosc"]/text()')[0]
                if language == "polski":
                    properties["languages"].append("pl") # is this right?

        return properties


class PWN(Source):
    name                    = 'PWN'
    description             = _('Downloads metadata and covers from ksiegarnia.pwn.pl')
    author                  = 'Adrianna Pińska'
    version                 = (1, 0, 0)
    minimum_calibre_version = (3, 0, 0)

    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(['title', 'authors', 'identifier:isbn', 'rating', 'publisher', 'pubdate', 'languages'])
    has_html_comments = True
    supports_gzip_transfer_encoding = True
    cached_cover_url_is_reliable = True

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        query = self.create_query(log, title=title, authors=authors, identifiers=identifiers)
        
        if query is None:
            log.error('Insufficient metadata to construct query')
            return

        log.info("Using query: %r" % query)
        
        urls = SearchResults.from_url(self.browser, query, timeout, log)

        if abort.is_set():
            return

        workers = [Worker(url, result_queue, self.browser, log, 1, self) for url in urls]

        for w in workers:
            w.start()
            # Don't send all requests at the same time
            time.sleep(0.1)

        while not abort.is_set():
            a_worker_is_alive = False
            for w in workers:
                w.join(0.2)
                if abort.is_set():
                    break
                if w.is_alive():
                    a_worker_is_alive = True
            if not a_worker_is_alive:
                break
        
        return None

    def create_query(self, log, title=None, authors=None, identifiers={}):
        print ('create_query')
        
        isbn = check_isbn(identifiers.get('isbn', None))
        if isbn:
            if len(isbn) == 13:
                return SearchResults.url_from_isbn13(isbn)
            elif len(isbn) == 10:
                return SearchResults.url_from_isbn10(isbn)
        
        else:
            title_tokens = list(self.get_title_tokens(title, strip_joiners=False, strip_subtitle=True))
            author_tokens = list(self.get_author_tokens(title, only_first_author=True))
            
            return SearchResults.url_from_title_and_author(title_tokens, author_tokens)        
    
    def download_cover(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        cached_url = None
        
        isbn = identifiers.get('isbn', None)
        
        if isbn:
            cached_url = self.cached_identifier_to_cover_url(isbn)
        
        if cached_url is None:
            log.info('No cached cover found, running identify')
            
            rq = Queue()
            self.identify(log, rq, abort, title=title, authors=authors, identifiers=identifiers)
            
            if abort.is_set():
                return
            
            results = []
            
            while True:
                try:
                    results.append(rq.get_nowait())
                except Empty:
                    break
                
            results.sort(key=self.identify_results_keygen(title=title, authors=authors, identifiers=identifiers))
            
            for mi in results:
                cached_url = self.get_cached_cover_url(mi.identifiers)
                if cached_url is not None:
                    break
        
        if cached_url is None:
            log.info('No cover found.')
            return

        if abort.is_set():
            return
                
        log('Downloading cover from:', cached_url)
        
        try:
            cdata = self.browser.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            log.exception('Failed to download cover from:', cached_url)


class Worker(Thread):
    '''
    Get book details from book page in a separate thread.
    '''

    def __init__(self, url, result_queue, browser, log, relevance, plugin, timeout=20):
        Thread.__init__(self)
        self.daemon = True
        self.url = url
        self.result_queue = result_queue
        self.log = log
        self.timeout = timeout
        self.relevance = relevance
        self.plugin = plugin
        self.browser = browser.clone_browser()

    def run(self):
        try:
            self.log.info('Worker parsing url: %r' % self.url)
            
            book = Book.from_url(self.browser, self.url, self.timeout, self.log)
            
            if not book.get("title") or not book.get("authors"):
                self.log.error('Insufficient metadata found for %r' % self.url)
                return
            
            title = book["title"].encode('utf-8')
            authors = [a.encode('utf-8') for a in book["authors"]]

            mi = Metadata(title, authors)
            
            isbn = book.get("ean") or book.get("isbn")
            if isbn:
                mi.set_identifier("isbn", isbn)
            
            for attr in ("pubdate", "rating", "languages"):
                if attr in book:
                    setattr(mi, attr, book[attr])
            
            if book.get("publisher"):
                mi.publisher = book["publisher"].encode('utf-8')
                    
            if book.get("cover_url"):
                self.plugin.cache_identifier_to_cover_url(isbn, book["cover_url"])
                mi.has_cover = True

            self.plugin.clean_downloaded_metadata(mi)
            self.result_queue.put(mi)
        except Exception as e:
            self.log.exception('Worker failed to fetch and parse url %r with error %r' % (self.url, e))
