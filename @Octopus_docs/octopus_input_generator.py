import json
import os

class OctopusInputGenerator:
    """
    Generates Octopus 'inp' files from frontend-style parameter dictionaries.
    """
    
    def __init__(self, output_dir="e:/PostGraduate/Dirac_solver/@Octopus_docs/generated_inputs"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generate_inp(self, config):
        """
        Maps frontend config to Octopus syntax.
        """
        lines = []
        
        # 1. Calculation Mode
        calc_mode = config.get("calcMode", config.get("octopusCalcMode", "gs"))
        lines.append(f"CalculationMode = {calc_mode}")
        
        # 2. Dimensionality
        dim = config.get("octopusDimensions", "3D")
        dim_val = "1" if dim == "1D" else ("2" if dim == "2D" else "3")
        lines.append(f"Dimensions = {dim_val}")
        
        # 3. Grid and Box
        spacing = config.get("octopusSpacing", 0.3)
        radius = config.get("octopusRadius", 5.0)
        box_shape = config.get("octopusBoxShape", "sphere")
        lines.append(f"Spacing = {spacing}")
        lines.append(f"Radius = {radius}")
        lines.append(f"BoxShape = {box_shape}")
        lines.append("")

        # 4. Periodic Boundary Conditions
        pbc = config.get("octopusPeriodic", "off")
        if pbc != "off" and pbc is not None:
            # map 'x' -> 'x', 'xy' -> 'xy', 'xyz' -> 'xyz'
            # if it was boolean True from old config, default to xyz
            pbc_val = "xyz" if pbc is True else str(pbc)
            lines.append(f"PeriodicBoundaries = {pbc_val}")
            lines.append("")
        
        # 5. Species and Coordinates
        engine_mode = config.get("engineMode", "local1D")
        
        if engine_mode == "octopus3D" and dim == "3D":
            molecule = config.get("molecule", config.get("octopusMolecule", "H2"))
            lines.append("%Coordinates")
            if molecule == "H":
                lines.append('  "H" | 0 | 0 | 0')
            elif molecule == "H2":
                lines.append('  "H" | 0 | 0 | -0.35')
                lines.append('  "H" | 0 | 0 | 0.35')
            elif molecule == "He":
                lines.append('  "He" | 0 | 0 | 0')
            elif molecule == "N2":
                lines.append('  "N" | 0 | 0 | -0.55')
                lines.append('  "N" | 0 | 0 | 0.55')
            elif molecule == "CH4":
                lines.append('  "C" | 0 | 0 | 0')
                lines.append('  "H" | 0.62 | 0.62 | 0.62')
                lines.append('  "H" | -0.62 | -0.62 | 0.62')
                lines.append('  "H" | -0.62 | 0.62 | -0.62')
                lines.append('  "H" | 0.62 | -0.62 | -0.62')
            elif molecule == "Benzene":
                lines.append('  "C" | 0.000000 |  1.397000 | 0.000000')
                lines.append('  "C" | 1.209838 |  0.698500 | 0.000000')
                lines.append('  "C" | 1.209838 | -0.698500 | 0.000000')
                lines.append('  "C" | 0.000000 | -1.397000 | 0.000000')
                lines.append('  "C" | -1.209838 | -0.698500 | 0.000000')
                lines.append('  "C" | -1.209838 |  0.698500 | 0.000000')
                lines.append('  "H" | 0.000000 |  2.481000 | 0.000000')
                lines.append('  "H" | 2.148609 |  1.240500 | 0.000000')
                lines.append('  "H" | 2.148609 | -1.240500 | 0.000000')
                lines.append('  "H" | 0.000000 | -2.481000 | 0.000000')
                lines.append('  "H" | -2.148609 | -1.240500 | 0.000000')
                lines.append('  "H" | -2.148609 |  1.240500 | 0.000000')
            lines.append("%")
        else:
            # 1D/2D Model System or 1D mode within Octopus
            potential_type = config.get("potentialType", "Harmonic")
            formula = self._get_potential_formula(potential_type, config)
            
            lines.append("%Species")
            lines.append(f'  "Particle" | species_user_defined | potential_formula | {formula} | valence | 1')
            lines.append("%")
            lines.append("")
            lines.append("%Coordinates")
            lines.append('  "Particle" | 0')
            lines.append("%")
            
        # 6. Output
        lines.append("")
        lines.append("%Output")
        lines.append("  wfs")
        lines.append("  potential")
        lines.append("%")
        lines.append("OutputFormat = axis_x")
        
        # 7. States & TD Evolution
        extra_states = config.get("octopusExtraStates", 4)
        lines.append(f"ExtraStates = {extra_states}")

        if calc_mode == "td":
            lines.append("")
            propagator = config.get("octopusPropagator", "aetrs")
            lines.append(f"TDPropagator = {propagator}")
            lines.append(f"TDMaxSteps = {config.get('octopusTdSteps', 100)}")
            dt = config.get("octopusTdTimeStep", 0.05)
            lines.append(f"TDTimeStep = {dt}")
            
        return "\n".join(lines)

    def _get_potential_formula(self, p_type, config):
        if p_type == "Harmonic":
            return '"0.5*x^2"'
        elif p_type == "InfiniteWell":
            hw = config.get("wellWidth", 1.0) / 2.0
            return f'"-1000*step({hw}-abs(x))"'
        return '"0"'

    def save_inp(self, config, filename="inp"):
        content = self.generate_inp(config)
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            f.write(content)
        return filepath

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, help="JSON config string")
    parser.add_argument("--out", type=str, default="inp", help="Output filename")
    args = parser.parse_args()
    
    generator = OctopusInputGenerator()
    if args.config:
        cfg = json.loads(args.config)
        path = generator.save_inp(cfg, args.out)
        print(f"Generated: {path}")
    else:
        # Default test
        test_config = {
            "engineMode": "octopus3D",
            "octopusCalcMode": "gs",
            "octopusDimensions": "3D",
            "octopusPeriodic": "xyz",
            "octopusSpacing": 0.5,
            "octopusRadius": 4.0,
            "octopusBoxShape": "sphere",
            "octopusMolecule": "H2"
        }
        path_test = generator.save_inp(test_config, "inp_test_pbc")
        print(f"Generated Test: {path_test}")
