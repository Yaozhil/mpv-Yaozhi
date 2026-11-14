ExternalProject_Add(mingw-w64
    GIT_REPOSITORY https://github.com/mingw-w64/mingw-w64.git
    GIT_TAG 7ce22f6637cc93fd2eb37c8a645908c92bb80bbd
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ""
    BUILD_COMMAND ""
    INSTALL_COMMAND ""
    LOG_DOWNLOAD 1 LOG_UPDATE 1
)

get_property(MINGW_SRC TARGET mingw-w64 PROPERTY _EP_SOURCE_DIR)
