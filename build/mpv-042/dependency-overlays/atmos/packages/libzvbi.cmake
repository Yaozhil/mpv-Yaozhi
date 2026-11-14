ExternalProject_Add(libzvbi
    DEPENDS
        libpng
        libiconv
    GIT_REPOSITORY https://github.com/zapping-vbi/zvbi.git
    GIT_TAG 34bb6f660c5c1bacd4a66cc7b22311e4ca3c1ab5
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    GIT_REMOTE_NAME origin
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ${EXEC} <SOURCE_DIR>/autogen.sh && CONF=1 <SOURCE_DIR>/configure
        --host=${TARGET_ARCH}
        --prefix=${MINGW_INSTALL_PREFIX}
        --disable-shared
        --enable-static
        --with-pic
        --without-doxygen
        --without-x
        --disable-dvb
        --disable-bktr
        --disable-nls
        --disable-proxy
        --disable-examples
        --disable-tests
    BUILD_COMMAND ${MAKE}
    INSTALL_COMMAND ${MAKE} install
    BUILD_IN_SOURCE 1
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

cleanup(libzvbi install)
