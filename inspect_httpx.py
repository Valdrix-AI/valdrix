import httpx
import asyncio

async def inspect():
    limits = httpx.Limits(max_connections=500, max_keepalive_connections=50)
    client = httpx.AsyncClient(limits=limits)
    print(f"Dir: {dir(client)}")
    # In some versions it's _limits or accessed via transport
    try:
        print(f"Limits: {client.limits}")
    except AttributeError:
        print("No .limits")
        
    try:
        print(f"_limits: {client._limits}")
    except AttributeError:
        print("No ._limits")
        
    # Check transport
    print(f"Transport: {type(client._transport)}")
    print(f"Transport Dir: {dir(client._transport)}")
    
    await client.aclose()

asyncio.run(inspect())
