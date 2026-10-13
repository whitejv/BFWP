# Host superbuild for the BFWP monorepo.
# This is not the ESP-IDF project. Firmware stays in bfwp-firmware/ and is built
# with the `firmware` target, which calls idf.py when IDF_PATH is set.
cmake_minimum_required(VERSION 3.20)
project(BFWP NONE)

set(BFWP_ROOT "${CMAKE_SOURCE_DIR}")

# One virtualenv per Python app. Apps without a pyproject.toml are skipped.
foreach(app IN ITEMS bfwp-twin bfwp-ingest bfwp-mcp)
  add_custom_target(${app}
    COMMAND /bin/sh "${BFWP_ROOT}/cmake/refresh-venv.sh" "${BFWP_ROOT}/${app}"
    COMMENT "Refreshing ${app}"
    VERBATIM
  )
endforeach()

add_custom_target(python-apps ALL
  DEPENDS bfwp-twin bfwp-ingest bfwp-mcp
)

# `cmake --build build --target install` refreshes the same virtualenvs.
# Nothing is copied to /usr/local; the prefix stays inside the build tree.
if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
  set(CMAKE_INSTALL_PREFIX "${CMAKE_BINARY_DIR}/install" CACHE PATH
    "Unused file prefix. Python apps install editable into each .venv." FORCE)
endif()
install(CODE "
  set(_rc 0)
  foreach(_app IN ITEMS bfwp-twin bfwp-ingest bfwp-mcp)
    execute_process(
      COMMAND /bin/sh \"${BFWP_ROOT}/cmake/refresh-venv.sh\" \"${BFWP_ROOT}/\${_app}\"
      RESULT_VARIABLE _one
    )
    if(NOT _one EQUAL 0)
      set(_rc \${_one})
    endif()
  endforeach()
  if(NOT _rc EQUAL 0)
    message(FATAL_ERROR \"venv refresh failed\")
  endif()
")

add_custom_target(test
  COMMAND /bin/sh "${BFWP_ROOT}/cmake/run-tests.sh" "${BFWP_ROOT}"
  DEPENDS python-apps
  COMMENT "Validating contracts and running app tests"
  VERBATIM
)

add_custom_target(firmware
  COMMAND /bin/sh "${BFWP_ROOT}/cmake/build-firmware.sh" "${BFWP_ROOT}"
  COMMENT "Building ESP-IDF firmware"
  VERBATIM
)

# Host-testable firmware logic joins this build once its CMakeLists exists.
if(EXISTS "${BFWP_ROOT}/bfwp-firmware/components/bfwp_core/CMakeLists.txt")
  enable_language(C)
  add_subdirectory(bfwp-firmware/components/bfwp_core)
endif()
