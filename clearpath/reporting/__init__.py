"""Person 3's entry points.

    from clearpath.reporting import gemini, report, channels
    obs = gemini.observe(reference_path, capture_path, comparison_dict)   # AI draft
    out = report.build(bundle, channel=channels.verified()[0])           # ReportOutput
    path = report.export(inspection_id, out)                             # printable HTML
"""
from . import channels, gemini, report  # noqa: F401
