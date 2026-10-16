from tests.conftest import LoginAs, MakeUser
from tests.integration.phase3_helpers import API_HEALTH, WEB_LOGIN, case_body, setup_project


async def test_suite_crud_and_ordering(make_user: MakeUser, login_as: LoginAs) -> None:
    await make_user("root@x.vn", admin=True)
    root = await login_as("root@x.vn")
    pid, _ = await setup_project(root, "https://demo.vn")
    a = (
        await root.post(f"/api/projects/{pid}/test-cases", json=case_body("A", API_HEALTH))
    ).json()["id"]
    b = (await root.post(f"/api/projects/{pid}/test-cases", json=case_body("B", WEB_LOGIN))).json()[
        "id"
    ]
    s = await root.post(
        f"/api/projects/{pid}/suites", json={"name": "Smoke", "test_case_ids": [b, a, b]}
    )
    assert s.status_code == 201
    sid = s.json()["id"]
    assert [i["test_case"]["id"] for i in s.json()["items"]] == [b, a]
    assert (
        await root.post(f"/api/projects/{pid}/suites", json={"name": "Smoke"})
    ).status_code == 409

    # Test case dự án khác bị từ chối.
    other = (await root.post("/api/projects", json={"key": "OT", "name": "O"})).json()["id"]
    await root.post(
        f"/api/projects/{other}/environments",
        json={"name": "D", "kind": "dev", "base_url": "https://o.vn"},
    )
    foreign = (
        await root.post(f"/api/projects/{other}/test-cases", json=case_body("F", API_HEALTH))
    ).json()["id"]
    assert (
        await root.put(f"/api/suites/{sid}/items", json={"test_case_ids": [foreign]})
    ).status_code == 422

    r = await root.put(f"/api/suites/{sid}/items", json={"test_case_ids": [a, b]})
    assert [i["position"] for i in r.json()["items"]] == [0, 1]
    lst = (await root.get(f"/api/projects/{pid}/suites")).json()
    assert lst[0]["case_count"] == 2

    # Xóa mềm test case thì gỡ khỏi suite.
    await root.delete(f"/api/test-cases/{a}")
    assert (await root.get(f"/api/suites/{sid}")).json()["case_count"] == 1
    assert (await root.get(f"/api/projects/{pid}/test-cases", params={"suite_id": sid})).json()[
        "total"
    ] == 1

    assert (await root.delete(f"/api/suites/{sid}")).status_code == 204
    assert (await root.get(f"/api/test-cases/{b}")).status_code == 200
