#!/bin/bash
set -e

cd /tmp
rm -rf octopus_test_td
mkdir -p octopus_test_td
cd octopus_test_td

echo "======================================="
echo "=== Step 1: Run Ground State (GS) ==="
echo "======================================="

cat > inp << 'INPUT'
Dimensions = 3
CalculationMode = gs
Radius = 5
Spacing = 0.5

%Species
  'H' | species_user_defined | potential_formula | "-1/sqrt(r^2+0.01)" | valence | 1
%

%Coordinates
 'H' | 0.0 | 0.0 | -0.7
 'H' | 0.0 | 0.0 | 0.7
%

LCAOReadWeights = no
XCFunctional = lda_x+lda_c_pz
ExtraStates = 2

%Output
  wfs
  density
%
OUTPUT

octopus 2>&1 | grep -E "(SCF|converged|Eigenvalue|returned)" | tail -5
GS_CODE=$?
echo "GS exit code: $GS_CODE"

if [ -f "static/info" ]; then
  echo "✓ GS produced static/info"
  grep "Eigenvalue" static/info | head -3
else
  echo "✗ ERROR: static/info not found"
  ls -la static/ 2>/dev/null || echo "No static dir exists"
  exit 1
fi

echo ""
echo "======================================="
echo "=== Step 2: Prepare TD (remove restart) ==="
echo "======================================="

echo "Restarting files before removal:"
ls -la restart 2>/dev/null | head -5 || echo "No restart dir"

rm -rf restart
echo "Removed restart dir"

echo ""
echo "======================================="
echo "=== Step 3: Run Time-Dependent (TD) ==="
echo "======================================="

cat > inp << 'INPUT'
Dimensions = 3
CalculationMode = td
Radius = 5
Spacing = 0.5

%Species
  'H' | species_user_defined | potential_formula | "-1/sqrt(r^2+0.01)" | valence | 1
%

%Coordinates
 'H' | 0.0 | 0.0 | -0.7
 'H' | 0.0 | 0.0 | 0.7
%

LCAOReadWeights = no
XCFunctional = lda_x+lda_c_pz
ExtraStates = 2
TDPropagator = aetrs
TDMaxSteps = 50
TDTimeStep = 0.05

%TDExternalFields
  electric_field | 1 | 0 | 0 | 0.05 | 'kick'
%

%TDFunctions
  'kick' | tdf_delta | 1.0
%

TDOutput = multipoles + energy
OUTPUT

echo "[INFO] Starting TD propagation..."
timeout 180 octopus 2>&1 | grep -E "(TD|time-step|returned|converged|Error)" | tail -10
TD_CODE=$?
echo "TD exit code: $TD_CODE"

if [ -d "td.general" ]; then
  echo "✓ TD created td.general directory"
  ls -la td.general/ | head -10
else
  echo "✗ ERROR: td.general directory not created"
  exit 1
fi

if [ -f "td.general/multipoles" ]; then
  echo "✓ TD produced multipoles"
  wc -l td.general/multipoles
else
  echo "✗ WARNING: multipoles not found"
fi

echo ""
echo "======================================="
echo "=== Step 4: Generate spectrum ==="
echo "======================================="

timeout 60 oct-propagation_spectrum 2>&1 | grep -E "(Error|SUCCESS|cross|returned)" | tail -5
SPEC_CODE=$?
echo "oct-propagation_spectrum exit code: $SPEC_CODE"

if [ -f "td.general/cross_section_vector" ]; then
  echo "✓ Spectrum generated cross_section_vector"
  wc -l td.general/cross_section_vector
  echo "First few lines:"
  head -3 td.general/cross_section_vector
else
  echo "✗ ERROR: cross_section_vector not created"
  echo "Directory contents:"
  ls -la td.general/ | tail -15
fi

echo ""
echo "======================================="
echo "=== SUMMARY ==="
echo "======================================="
echo "GS exit: $GS_CODE"
echo "TD exit: $TD_CODE"
echo "Spectrum exit: $SPEC_CODE"
