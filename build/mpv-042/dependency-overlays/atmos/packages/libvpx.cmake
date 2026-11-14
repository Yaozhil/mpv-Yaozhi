ExternalProject_Add(libvpx
    GIT_REPOSITORY https://chromium.googlesource.com/webm/libvpx.git
    GIT_TAG 8c9ef99ff058c2059395cab9637dc52ca223a520
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    GIT_REMOTE_NAME origin
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ${EXEC} CONF=1 CROSS=${TARGET_ARCH}- <SOURCE_DIR>/configure
        --extra-cflags='-fno-asynchronous-unwind-tables'
        --target=${libvpx_target}
        --prefix=${MINGW_INSTALL_PREFIX}
        --disable-examples
        --disable-docs
        --disable-tools
        --disable-unit-tests
        --disable-decode-perf-tests
        --disable-encode-perf-tests
        --as=yasm
        --enable-debug
        --enable-vp9-highbitdepth
    BUILD_COMMAND ${MAKE}
    INSTALL_COMMAND ${MAKE} install
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

cleanup(libvpx install)
