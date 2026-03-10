import os
import re

def analyze_octopus_results(output_dir):
    print("="*60)
    print("      Octopus 计算结果自动化分析报告 (Octopus Result Analysis)")
    print("="*60)

    info_path = os.path.join(output_dir, "info")
    conv_path = os.path.join(output_dir, "convergence")
    dos_path = os.path.join(output_dir, "total-dos.dat")

    # 1. 分析 info 文件
    if os.path.exists(info_path):
        with open(info_path, 'r') as f:
            content = f.read()
            
            # 收敛状态
            converged = "SCF converged!" in content
            print(f"[1] 收敛状态: {'✅ 已收敛 (Converged)' if converged else '❌ 未收敛 (NOT Converged)'}")
            
            # 总能量
            total_energy_match = re.search(r"Total\s+=\s+(-?\d+\.\d+)", content)
            if total_energy_match:
                print(f"[2] 体系总能量 (Total Energy): {total_energy_match.group(1)} Hartree")
            
            # 本征值分析
            eigen_header = re.search(r"Eigenvalues \[H\]\s+#st\s+Spin\s+Eigenvalue\s+Occupation", content)
            if eigen_header:
                print("\n[3] 关键能级轨道 (Key Eigenvalues):")
                lines = content.split('\n')
                idx = lines.index(next(l for l in lines if "#st" in l and "Spin" in l))
                homo = None
                lumo = None
                for line in lines[idx+1:]:
                    parts = line.split()
                    if len(parts) >= 4:
                        st, spin, val, occ = parts[0], parts[1], float(parts[2]), float(parts[3])
                        if occ > 0.1:
                            homo = val
                        elif occ < 0.1 and lumo is None:
                            lumo = val
                            break
                if homo is not None and lumo is not None:
                    print(f"    - HOMO (最高占据): {homo} H")
                    print(f"    - LUMO (最低未占据): {lumo} H")
                    print(f"    - 能隙 (Energy Gap): {round(abs(lumo - homo), 5)} H (~{round(abs(lumo-homo)*27.21, 2)} eV)")

    # 2. 分析收敛轨迹
    if os.path.exists(conv_path):
        with open(conv_path, 'r') as f:
            lines = f.readlines()
            if len(lines) > 1:
                last_line = lines[-1].split()
                if len(last_line) >= 4:
                    print(f"\n[4] 最终收敛精度 (Final Precision):")
                    print(f"    - 能量差 (Energy Diff): {last_line[2]}")
                    print(f"    - 密度差 (Density Diff): {last_line[3]}")

    # 3. 分析 DOS
    if os.path.exists(dos_path):
        print(f"\n[5] 态密度文件 (DOS): 已检测到 '{os.path.basename(dos_path)}'")
        print("    - 建议使用 Python/Gnuplot 绘制该数据以查看能带分布。")

    print("\n" + "="*60)
    print("分析完成。请参考 @Octopus_docs 中的 Operation_Handbook 进行优化。")

if __name__ == "__main__":
    # 默认分析当前目录下的 output
    target = os.path.join(os.getcwd(), "output")
    if not os.path.exists(target):
        # 尝试父目录或指定路径
        target = r"e:\PostGraduate\Dirac_solver\@Octopus_docs\output"
    
    analyze_octopus_results(target)
