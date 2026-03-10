import asyncio, json
import server

config = {
    "engineMode": "octopus3D",
    "moleculeName": "H2",
    "calcMode": "gs"
}

async def main():
    print("Running Octopus H2 Ground State...")
    res = await server.run_octopus_calculation(config)
    print("--- STDOUT TAIL ---")
    print(res.get("stdout_tail", ""))
    print("--- STDERR TAIL ---")
    print(res.get("stderr_tail", ""))
    print("--- STATUS ---")
    print(res.get("status"))

if __name__ == "__main__":
    asyncio.run(main())
