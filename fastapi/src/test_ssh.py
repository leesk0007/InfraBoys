import asyncio
import sys
import asyncssh
import data_handler

async def test():
    try:
        async with asyncssh.connect(
            "10.0.10.205", 
            username="ec2-user", 
            client_keys=["/app/keys/ansible_key"],
            known_hosts=None
        ) as conn:
            result = await conn.run("whoami", check=False)
            print("Ansible Key Success:", result.stdout)
    except Exception as e:
        print("Ansible Key Error:", e)

asyncio.run(test())
