"""sars_convert.

Convert pdf2html fixed-layout HTML dumps of Tanzanian school-ranking reports
into clean, semantic HTML+CSS and render them to A4 PDFs with WeasyPrint.

The package is organised into three stages:

* :mod:`sars_convert.converter` - parse the mess pdf2html HTML and reconstruct
  clean semantic HTML+CSS (tables where the data is tabular).
* :mod:`sars_convert.render` - render the clean HTML to A4 PDF (landscape or
  portrait per document) with WeasyPrint.
* :mod:`sars_convert.verify` - compare the rendered PDF against the reference
  PDF (ground truth) for fidelity.
"""

__version__ = "0.1.0"
