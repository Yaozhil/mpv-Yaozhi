ExternalProject_Add(dav1d
    DEPENDS
        xxhash
    GIT_REPOSITORY https://code.videolan.org/videolan/dav1d.git
    GIT_TAG 9433da2daa61bf7029a52b84bafa5daf59cdcc9d
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ${EXEC} CONF=1 meson setup <BINARY_DIR> <SOURCE_DIR>
        --prefix=${MINGW_INSTALL_PREFIX}
        --libdir=${MINGW_INSTALL_PREFIX}/lib
        --cross-file=${MESON_CROSS}
        --buildtype=release
        --default-library=static
        -Denable_tools=false
        -Denable_tests=false
        -Dxxhash_muxer=enabled
    BUILD_COMMAND ${EXEC} ninja -C <BINARY_DIR>
    INSTALL_COMMAND ${EXEC} ninja -C <BINARY_DIR> install
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

force_meson_configure(dav1d)
cleanup(dav1d install)
