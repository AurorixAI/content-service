import sys
import logging
logging.basicConfig(level=logging.INFO)
import os
from src.pipeline.toc_extractor import extract_toc

pdf = "/textbooks/9_grade/7fb9904d29_algebra_9_klass_ju_n_makarychev_2023_g_.pdf"
toc = extract_toc(pdf)
print("TOC entries count:", len(toc))
print("TOC:", toc)
