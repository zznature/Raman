"""
Manual CLI for moving the MC.NewtonLT-06 Z stage.

Run from the raman directory:
    python -m tests.z_stage_manual --port COM3 --move 10.5
    python -m tests.z_stage_manual --port COM3 --move -20
"""

import argparse

from stage.z_stage import ZStageController


def main():
    parser = argparse.ArgumentParser(description="Move the MC.NewtonLT-06 Z stage.")
    parser.add_argument("--port", required=True, help="Serial port, for example COM3")
    parser.add_argument("--move", type=float, required=True, help="Relative Z move in um")
    args = parser.parse_args()

    with ZStageController(port=args.port) as z_stage:
        pos_before = z_stage.get_position_um()
        print(f"Position before: {pos_before:.3f} um")
        z_stage.move_relative_um(args.move)
        z_stage.wait_settled(timeout_ms=3000)
        pos_after = z_stage.get_position_um()
        print(f"Position after: {pos_after:.3f} um")
        print(f"Actual move: {pos_after - pos_before:.3f} um")


if __name__ == "__main__":
    main()
