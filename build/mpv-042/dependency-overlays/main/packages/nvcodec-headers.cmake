ExternalProject_Add(nvcodec-headers
    GIT_REPOSITORY https://github.com/FFmpeg/nv-codec-headers.git
    GIT_TAG 71acc268a541f7d7f33cf0387229e3015cfb4977
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ""
    BUILD_COMMAND ""
    INSTALL_COMMAND ${MAKE} -C <SOURCE_DIR>
        PREFIX=${MINGW_INSTALL_PREFIX}
        install
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

cleanup(nvcodec-headers install)
