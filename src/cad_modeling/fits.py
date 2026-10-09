"""Fit system: hole clearances and allowances.

Through-bolt holes follow the ISO 273 series. Tapped features are modeled
at tap-drill size. Allowances are chosen for laser-cut acrylic and FDM
parts, both of which close up small holes.
"""

# ISO 273 clearance holes
M3_MEDIUM = 3.4   # general through bolt
M2_5_MEDIUM = 2.9 # GY-521's D3 holes use M2.5 hardware

# tapped features, modeled at tap-drill size
M3_TAP_DRILL = 2.5
