import asyncio
import os
from shared.db import get_pool

async def check():
    pool = await get_pool()
    async with pool.acquire() as conn:
        print("Checking public.parcels_cliplayer:")
        rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'parcels_cliplayer'")
        print([r['column_name'] for r in rows])
        
        print("\nChecking public.parcels_clean:")
        rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'parcels_clean'")
        print([r['column_name'] for r in rows])
        
        print("\nChecking public.parcel_damage:")
        rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'parcel_damage'")
        print([r['column_name'] for r in rows])

    await pool.close()

if __name__ == "__main__":
    asyncio.run(check())
