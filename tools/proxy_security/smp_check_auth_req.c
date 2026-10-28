/******************************************************************************
 *
 *  Copyright (C) 2003-2012 Broadcom Corporation
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at:
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 *
 ******************************************************************************/

/* Extracted from ESP-IDF v5.5.6, stack/smp/smp_act.c.
 * Source: https://github.com/espressif/esp-idf/blob/v5.5.6/components/bt/host/bluedroid/stack/smp/smp_act.c
 */
void smp_check_auth_req(tSMP_CB *p_cb, tSMP_INT_DATA *p_data)
{
    UINT8 enc_enable = *(UINT8 *)p_data;
    UINT8 reason = enc_enable ? SMP_SUCCESS : SMP_ENC_FAIL;

    SMP_TRACE_DEBUG("%s rcvs enc_enable=%d i_keys=0x%x r_keys=0x%x "
                    "(i-initiator r-responder)\n",
                    __func__, enc_enable, p_cb->local_i_key, p_cb->local_r_key);
    if (enc_enable == 1) {
#if (BLE_INCLUDED == TRUE)
        /* The new pairing has been authenticated and the link is now encrypted with the
           freshly generated key, so the previous bond can be dropped. Doing it here rather
           than when the Pairing Request is exchanged keeps the old key in place for a
           pairing that never completes. */
        tBTM_SEC_DEV_REC *p_dev_rec = btm_find_dev(p_cb->pairing_bda);
        if (p_dev_rec) {
            if (p_dev_rec->ble.key_type & (BTM_LE_KEY_PENC | BTM_LE_KEY_LENC)) {
                SMP_TRACE_DEBUG("LE replace bond after enc, BDA:0x%02X%02X%02X%02X%02X%02X",
                                p_cb->pairing_bda[0], p_cb->pairing_bda[1], p_cb->pairing_bda[2],
                                p_cb->pairing_bda[3], p_cb->pairing_bda[4], p_cb->pairing_bda[5]);
            }
            btm_sec_clear_ble_keys(p_dev_rec);
        }
#endif  ///BLE_INCLUDED == TRUE

        if (p_cb->le_secure_connections_mode_is_used) {
            /* In LE SC mode LTK is used instead of STK and has to be always saved */
            p_cb->local_i_key |= SMP_SEC_KEY_TYPE_ENC;
            p_cb->local_r_key |= SMP_SEC_KEY_TYPE_ENC;

            /* In LE SC mode LK is derived from LTK only if both sides request it */
            if (!(p_cb->local_i_key & SMP_SEC_KEY_TYPE_LK) ||
                    !(p_cb->local_r_key & SMP_SEC_KEY_TYPE_LK)) {
                p_cb->local_i_key &= ~SMP_SEC_KEY_TYPE_LK;
                p_cb->local_r_key &= ~SMP_SEC_KEY_TYPE_LK;
            }

            /* In LE SC mode only IRK, IAI, CSRK are exchanged with the peer.
            ** Set local_r_key on master to expect only these keys.
            */
            if (p_cb->role == HCI_ROLE_MASTER) {
                p_cb->local_r_key &= (SMP_SEC_KEY_TYPE_ID | SMP_SEC_KEY_TYPE_CSRK);
            }
        } else {
            /* in legacy mode derivation of BR/EDR LK is not supported */
            p_cb->local_i_key &= ~SMP_SEC_KEY_TYPE_LK;
            p_cb->local_r_key &= ~SMP_SEC_KEY_TYPE_LK;
        }
        SMP_TRACE_DEBUG("%s rcvs upgrades: i_keys=0x%x r_keys=0x%x "
                        "(i-initiator r-responder)\n",
                        __func__, p_cb->local_i_key, p_cb->local_r_key);

        if (/*((p_cb->peer_auth_req & SMP_AUTH_BOND) ||
             (p_cb->loc_auth_req & SMP_AUTH_BOND)) &&*/
            (p_cb->local_i_key || p_cb->local_r_key)) {
            smp_sm_event(p_cb, SMP_BOND_REQ_EVT, NULL);
        } else {
            smp_sm_event(p_cb, SMP_AUTH_CMPL_EVT, &reason);
        }
    } else if (enc_enable == 0) {
        /* if failed for encryption after pairing, send callback */
        if (p_cb->flags & SMP_PAIR_FLAG_ENC_AFTER_PAIR) {
            smp_sm_event(p_cb, SMP_AUTH_CMPL_EVT, &reason);
        }
        /* if enc failed for old security information */
        /* if master device, clean up and abck to idle; slave device do nothing */
        else if (p_cb->role == HCI_ROLE_MASTER) {
            smp_sm_event(p_cb, SMP_AUTH_CMPL_EVT, &reason);
        }
    }
}


