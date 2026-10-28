#pragma once

// host.wokwi.internal is reachable from Wokwi only through its Private IoT Gateway.
#define WOKWI_API_HOST "host.wokwi.internal"
#define WOKWI_API_PORT 8001
#define WOKWI_API_ROUTE "/reading"
#define WOKWI_DEVICE_ID "wokwi-esp32-01"
#define SIMULATED_VOLTAGE_V 230.0f
#define WOKWI_SEND_INTERVAL_MS 1000UL
#define WOKWI_HTTP_TIMEOUT_MS 2500
#define WOKWI_DNS_RETRY_INTERVAL_MS 10000UL
