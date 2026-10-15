"""Restrained accents around native Qt controls.

Input geometry, arrows, headers and tabs are deliberately owned by QStyle.
Overriding their borders/padding without all sub-controls breaks hit testing on
some Windows styles. Font and spacing are configured by the layouts, in logical
units, so display scaling does not crop a table row or overlap spin arrows.
"""

STYLESHEET = """
QLabel#sectionTitle { font-weight: 600; }
QLabel#muted { color: #58656c; }
QLabel#metric { font-size: 18pt; font-weight: 700; }
QLabel#status { color: #675413; background: #fff8df; padding: 1px 3px; }
QLabel#error { color: #962c24; background: #fff0ed; padding: 1px 3px; }
QLabel#pickerHeading { font-weight: 600; }
QToolTip { padding: 2px; }
"""
