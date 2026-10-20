async def test_qr_create_image_scan(client, auth):
    r = await client.post("/qrcode/", json={"target_url": "https://www.cmu.edu/", "color": "#2E4BC8", "style": "dots"}, headers=auth)
    assert r.status_code == 201
    q = r.json()
    assert q["qr_code_id"].startswith("qr") and q["qr_code_url"].endswith(f"/qrcode/{q['qr_code_id']}")
    img = await client.get(f"/qrcode/{q['qr_code_id']}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[:8] == b"\x89PNG\r\n\x1a\n"
    scan = await client.get(f"/qrcode/{q['qr_code_id']}", headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile"})
    assert scan.status_code == 307 and scan.headers["location"] == "https://www.cmu.edu/"
    hist = (await client.get("/qrcodes/history", headers=auth)).json()
    assert hist["total"] == 1 and hist["qrcodes"][0]["scans"] == 1
    stats = (await client.get(f"/analytics/qrcode/{q['qr_code_id']}", headers=auth)).json()
    assert stats["scans"] == 1 and stats["scan_data"]["devices"] == [{"type": "mobile", "count": 1}]


async def test_qr_validation_and_delete(client, auth):
    assert (await client.post("/qrcode/", json={"target_url": "https://x.com", "color": "blue"}, headers=auth)).status_code == 422
    q = (await client.post("/qrcode/", json={"target_url": "https://example.com/q"}, headers=auth)).json()
    assert (await client.delete(f"/qrcode/{q['qr_code_id']}", headers=auth)).status_code == 204
    assert (await client.get(f"/qrcode/{q['qr_code_id']}/image")).status_code == 404


async def test_qr_preview_requires_auth_and_renders(client, auth):
    assert (await client.get("/qrcode/preview?target_url=https://example.com")).status_code == 401
    r = await client.get("/qrcode/preview?target_url=https://example.com&color=%23DC2626&style=rounded", headers=auth)
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
