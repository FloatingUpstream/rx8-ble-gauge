"""Portable scratch outputs and metadata for original project CAD."""

import os
from pathlib import Path


def aux_root():
    """GAUGE_AUX overrides the ignored repository-local scratch directory."""
    return Path(os.environ.get("GAUGE_AUX", Path(__file__).resolve().parents[1] / ".local/aux"))


def prototype_output(name):
    return aux_root() / "mechanical" / name


def public_metadata(doc):
    doc.CreatedBy = ""
    doc.LastModifiedBy = ""
    doc.Company = ""
    doc.License = "The Unlicense"
    doc.LicenseURL = "https://unlicense.org/"
