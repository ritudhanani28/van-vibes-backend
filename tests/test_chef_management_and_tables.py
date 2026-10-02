import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def _get_admin_token():
    res = client.post('/api/v1/auth/login', json={'email': 'admin@vaanvibes.com', 'password': 'admin123'})
    assert res.status_code == 200
    return res.json()['access_token']

def test_admin_can_create_chef_account_and_chef_can_login():
    admin_token = _get_admin_token()
    import uuid
    email = f'chef_test_{uuid.uuid4().hex[:8]}@vaanvibes.com'

    # 1. Admin creates chef
    payload = {
        'name': 'Chef Sanjeev',
        'email': email,
        'contact_number': '9876543299',
        'password': 'ChefPassword@123',
    }
    create_res = client.post('/api/v1/auth/chefs', json=payload, headers={'Authorization': f'Bearer {admin_token}'})
    # If already exists from previous run, that's fine or handle
    if create_res.status_code == 400:
        # already exists
        pass
    else:
        assert create_res.status_code == 201
        data = create_res.json()
        assert data['name'] == 'Chef Sanjeev'
        assert data['role'] == 'CHEF'
        assert data['contact_number'] == '9876543299'
        assert 'password' not in data
        assert 'password_hash' not in data

    # 2. Chef logs in
    login_res = client.post('/api/v1/auth/login', json={'email': email, 'password': 'ChefPassword@123'})
    assert login_res.status_code == 200
    chef_token = login_res.json()['access_token']
    assert login_res.json()['user']['role'] == 'CHEF'

    # 3. Chef changes password
    change_res = client.post(
        '/api/v1/auth/change-password',
        headers={'Authorization': f'Bearer {chef_token}'},
        json={
            'current_password': 'ChefPassword@123',
            'new_password': 'NewChefPassword@123',
            'confirm_new_password': 'NewChefPassword@123',
        }
    )
    assert change_res.status_code == 200
    assert 'successfully' in change_res.json()['message'].lower()

    # 4. Chef logs in with new password
    new_login_res = client.post('/api/v1/auth/login', json={'email': email, 'password': 'NewChefPassword@123'})
    assert new_login_res.status_code == 200

    # 5. Chef cannot access admin endpoints
    chef_new_token = new_login_res.json()['access_token']
    forbidden_res = client.get('/api/v1/auth/chefs', headers={'Authorization': f'Bearer {chef_new_token}'})
    assert forbidden_res.status_code == 403

def test_admin_add_table_and_qr_generation():
    admin_token = _get_admin_token()
    table_num = 99

    res = client.post(
        '/api/v1/tables',
        headers={'Authorization': f'Bearer {admin_token}'},
        json={'tableNumber': table_num, 'capacity': 6}
    )
    if res.status_code == 400 and 'already exists' in res.text:
        # already created
        pass
    else:
        assert res.status_code == 201
        tbl = res.json()
        assert tbl['tableNumber'] == table_num
        assert tbl['status'] == 'AVAILABLE'
        assert tbl['token'].startswith('vv_sec_')

    # Duplicate creation rejected
    dup_res = client.post(
        '/api/v1/tables',
        headers={'Authorization': f'Bearer {admin_token}'},
        json={'tableNumber': table_num, 'capacity': 6}
    )
    assert dup_res.status_code == 400

    # QR generation
    qr_res = client.get(f'/api/v1/tables/T{table_num}/qr')
    assert qr_res.status_code == 200
    assert qr_res.headers['content-type'] == 'image/png'

def test_admin_delete_table():
    import random
    admin_token = _get_admin_token()
    # Find unused table number
    list_res = client.get('/api/v1/tables')
    existing_nums = {t['tableNumber'] for t in list_res.json()} if list_res.status_code == 200 else set()
    table_num = 200
    while table_num in existing_nums:
        table_num += 1

    # Create table
    res = client.post(
        '/api/v1/tables',
        headers={'Authorization': f'Bearer {admin_token}'},
        json={'tableNumber': table_num, 'capacity': 4}
    )
    if res.status_code != 201:
        # If ID conflict due to inactive table, try random high numbers
        for alt in range(300, 400):
            res = client.post(
                '/api/v1/tables',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'tableNumber': alt, 'capacity': 4}
            )
            if res.status_code == 201:
                table_num = alt
                break

    assert res.status_code == 201
    table_id = res.json()['id']

    # Delete table as admin
    del_res = client.delete(
        f'/api/v1/tables/{table_id}',
        headers={'Authorization': f'Bearer {admin_token}'}
    )
    assert del_res.status_code == 200
    assert 'deleted successfully' in del_res.json()['message']

    # Table is no longer in active tables list
    list_res = client.get('/api/v1/tables')
    assert list_res.status_code == 200
    table_ids = [t['id'] for t in list_res.json()]
    assert table_id not in table_ids


def test_admin_update_and_delete_chef():
    admin_token = _get_admin_token()
    import uuid
    email = f'chef_crud_{uuid.uuid4().hex[:8]}@vaanvibes.com'

    # Create chef
    payload = {
        'name': 'Chef Ranveer',
        'email': email,
        'contact_number': '9876543210',
        'role': 'CHEF',
        'password': 'ChefPassword@123',
    }
    create_res = client.post('/api/v1/auth/chefs', json=payload, headers={'Authorization': f'Bearer {admin_token}'})
    assert create_res.status_code == 201
    chef_data = create_res.json()
    chef_id = chef_data['id']
    assert chef_data['name'] == 'Chef Ranveer'

    # Update chef
    update_payload = {
        'name': 'Chef Ranveer Brar',
        'email': email,
        'contact_number': '9123456789',
        'role': 'CHEF',
        'shift': 'Evening',
        'assigned_station': 'Tandoor & Grill',
        'is_active': True,
    }
    update_res = client.put(f'/api/v1/auth/chefs/{chef_id}', json=update_payload, headers={'Authorization': f'Bearer {admin_token}'})
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data['name'] == 'Chef Ranveer Brar'
    assert updated_data['contact_number'] == '9123456789'
    assert updated_data['assigned_station'] == 'Tandoor & Grill'

    # Delete chef
    delete_res = client.delete(f'/api/v1/auth/chefs/{chef_id}', headers={'Authorization': f'Bearer {admin_token}'})
    assert delete_res.status_code == 200
    assert 'deleted successfully' in delete_res.json()['message']

    # Verify not in list
    list_res = client.get('/api/v1/auth/chefs', headers={'Authorization': f'Bearer {admin_token}'})
    assert list_res.status_code == 200
    ids = [c['id'] for c in list_res.json()]
    assert chef_id not in ids
