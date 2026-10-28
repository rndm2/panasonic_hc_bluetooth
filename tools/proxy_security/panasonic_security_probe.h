#pragma once

#include "esphome/components/ble_client/ble_client.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"

// Diagnostic node only: no pairing, bond removal, HVAC commands or auto-connect.
class PanasonicSecurityProbe : public esphome::ble_client::BLEClientNode {
 public:
  explicit PanasonicSecurityProbe(esphome::ble_client::BLEClient *parent) {
    parent->register_ble_node(this);
  }

  void start() {
    if (pending_ || blocked_ || cccd_ == 0 || parent()->state() != esphome::esp32_ble_tracker::ClientState::ESTABLISHED) {
      ESP_LOGW("panasonic_security", "Protected CCCD test refused: ready=%d pending=%d handle=%u",
               parent()->state() == esphome::esp32_ble_tracker::ClientState::ESTABLISHED, pending_, cccd_);
      return;
    }
    submit_(1);
  }

  void loop() override {
    if (pending_ && esphome::millis() - started_ >= 10000) {
      ESP_LOGW("panasonic_security", "Protected CCCD test timed out, phase=%u", phase_);
      pending_ = false;
      blocked_ = true;  // A late completion must not be assigned to a new test.
    }
  }

  void gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t,
                           esp_ble_gattc_cb_param_t *param) override {
    if (event == ESP_GATTC_SEARCH_CMPL_EVT) {
      cccd_ = 0;
      blocked_ = false;
      if (param->search_cmpl.status == ESP_GATT_OK) {
        using esphome::esp32_ble_tracker::ESPBTUUID;
        esp_gattc_char_elem_t characteristic{};
        uint16_t count = 1;
        auto uuid = ESPBTUUID::from_raw("4d200003-eff3-4362-b090-a04cab3f1da0").get_uuid();
        auto status = esp_ble_gattc_get_char_by_uuid(parent()->get_gattc_if(), parent()->get_conn_id(),
                                                    1, 0xffff, uuid, &characteristic, &count);
        if (status == ESP_GATT_OK && count == 1) {
          esp_gattc_descr_elem_t descriptor{};
          count = 1;
          auto cccd_uuid = ESPBTUUID::from_uint16(0x2902).get_uuid();
          status = esp_ble_gattc_get_descr_by_char_handle(parent()->get_gattc_if(), parent()->get_conn_id(),
                                                         characteristic.char_handle, cccd_uuid, &descriptor, &count);
          if (status == ESP_GATT_OK && count == 1) cccd_ = descriptor.handle;
        }
      }
      node_state = esphome::esp32_ble_tracker::ClientState::ESTABLISHED;
      ESP_LOGI("panasonic_security", "Protected CCCD test discovered handle=%u", cccd_);
    } else if (event == ESP_GATTC_WRITE_DESCR_EVT && pending_ &&
               param->write.conn_id == conn_id_ && param->write.handle == cccd_) {
      pending_ = false;
      ESP_LOGI("panasonic_security", "Protected CCCD write completed: enable=%u status=%u", phase_, param->write.status);
      if (phase_ == 1 && param->write.status == ESP_GATT_OK) submit_(0);
    } else if (event == ESP_GATTC_CLOSE_EVT || event == ESP_GATTC_DISCONNECT_EVT) {
      if (pending_) ESP_LOGW("panasonic_security", "Protected CCCD test aborted by disconnect");
      pending_ = false;
      blocked_ = false;
      cccd_ = 0;
    }
  }

 protected:
  void submit_(uint8_t enable) {
    uint8_t value[2] = {enable, 0};
    phase_ = enable;
    conn_id_ = parent()->get_conn_id();
    pending_ = true;
    started_ = esphome::millis();
    auto result = esp_ble_gattc_write_char_descr(parent()->get_gattc_if(), conn_id_, cccd_, sizeof(value), value,
                                                ESP_GATT_WRITE_TYPE_RSP, ESP_GATT_AUTH_REQ_NONE);
    ESP_LOGI("panasonic_security", "Protected CCCD write submitted: enable=%u result=%d", enable, result);
    if (result != ESP_OK) pending_ = false;
  }

  uint16_t cccd_{0};
  uint16_t conn_id_{0};
  uint8_t phase_{0};
  bool pending_{false};
  bool blocked_{false};
  uint32_t started_{0};
};

inline PanasonicSecurityProbe *panasonic_security_probe = nullptr;
