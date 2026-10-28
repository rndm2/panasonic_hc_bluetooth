"""Execute the actual SDK handler with stubbed surrounding stack calls."""

import subprocess
import tempfile
from pathlib import Path

from sdk_bond_fix import fix_source

root = Path(__file__).parent
original = (root / "smp_check_auth_req.c").read_text()

patched = fix_source(original)
stubs = r"""
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t UINT8;
typedef UINT8 tSMP_INT_DATA;
typedef struct { struct { UINT8 key_type; } ble; } tBTM_SEC_DEV_REC;
typedef struct { UINT8 pairing_bda[6],flags,local_i_key,local_r_key,role,le_secure_connections_mode_is_used; } tSMP_CB;
#define BLE_INCLUDED 1
#define TRUE 1
#define SMP_SUCCESS 0
#define SMP_ENC_FAIL 1
#define SMP_PAIR_FLAG_ENC_AFTER_PAIR 16
#define BTM_LE_KEY_PENC 1
#define BTM_LE_KEY_LENC 16
#define SMP_SEC_KEY_TYPE_ENC 1
#define SMP_SEC_KEY_TYPE_ID 2
#define SMP_SEC_KEY_TYPE_CSRK 4
#define SMP_SEC_KEY_TYPE_LK 8
#define HCI_ROLE_MASTER 0
#define SMP_BOND_REQ_EVT 10
#define SMP_AUTH_CMPL_EVT 11
#define SMP_TRACE_DEBUG(...) ((void)0)
static tBTM_SEC_DEV_REC record;
static int clears,last_event;
static tBTM_SEC_DEV_REC *btm_find_dev(UINT8 *address) { (void)address; return &record; }
static void btm_sec_clear_ble_keys(tBTM_SEC_DEV_REC *rec) { clears++; rec->ble.key_type=0; }
static void smp_sm_event(tSMP_CB *cb, int event, UINT8 *data) { (void)cb;(void)data;last_event=event; }
"""
cases = r"""
int main(void) {
 tSMP_CB cb={0}; UINT8 encrypted=1;
 record.ble.key_type=BTM_LE_KEY_PENC;
 smp_check_auth_req(&cb,&encrypted);
 if(clears || record.ble.key_type!=BTM_LE_KEY_PENC) {
  puts("FAIL: reusing a bonded key erased RAM keys"); return 1;
 }
 if(last_event!=SMP_AUTH_CMPL_EVT) return 2;
 clears=0; cb.flags=SMP_PAIR_FLAG_ENC_AFTER_PAIR;cb.local_i_key=SMP_SEC_KEY_TYPE_ENC;
 smp_check_auth_req(&cb,&encrypted);
 if(clears!=1 || record.ble.key_type!=0 || last_event!=SMP_BOND_REQ_EVT) return 3;
 clears=0;record.ble.key_type=BTM_LE_KEY_PENC;encrypted=0;
 smp_check_auth_req(&cb,&encrypted);
 if(clears || record.ble.key_type!=BTM_LE_KEY_PENC || last_event!=SMP_AUTH_CMPL_EVT) return 4;
 puts("PASS: retain reused bond, replace only after new pairing, retain on failed encryption");
 return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="panasonic-sdk-test-") as tmp:
    for name, handler, expected in [("original", original, 1), ("patched", patched, 0)]:
        src = Path(tmp) / f"{name}.c"
        binary = Path(tmp) / name
        src.write_text(stubs + handler + cases)
        subprocess.run(
            ["cc", "-std=c99", "-Wall", "-Wextra", str(src), "-o", str(binary)], check=True
        )
        run = subprocess.run([str(binary)], text=True, capture_output=True)
        print(name + ": " + run.stdout.strip())
        assert run.returncode == expected, (name, run.returncode, run.stderr)
