ExternalProject_Add(avs3-audiodec
    GIT_REPOSITORY https://github.com/lioumin1/Sourcecodeforplayer.git
    GIT_TAG e7d244d29454eb04c968cd98a30587303a9c15f8
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--sparse --filter=blob:none"
    GIT_CLONE_POST_COMMAND
        "sparse-checkout set av3adecoder av3a_binaural_render/AudioDecoder/av3a_binaural_render"
    UPDATE_COMMAND ""
    PATCH_COMMAND ${EXEC} python3
        ${CMAKE_CURRENT_SOURCE_DIR}/avs3-normalize-source-eol.py
        <SOURCE_DIR>
        COMMAND ${EXEC} git apply --check
        ${CMAKE_CURRENT_SOURCE_DIR}/avs3-audiodec-9000-static-library.patch
        COMMAND ${EXEC} git apply
        ${CMAKE_CURRENT_SOURCE_DIR}/avs3-audiodec-9000-static-library.patch
        COMMAND ${EXEC} git apply --check
        ${CMAKE_CURRENT_SOURCE_DIR}/avs3-audiodec-9001-spatial-metadata.patch
        COMMAND ${EXEC} git apply
        ${CMAKE_CURRENT_SOURCE_DIR}/avs3-audiodec-9001-spatial-metadata.patch
        COMMAND ${EXEC} git apply --check
        ${CMAKE_CURRENT_SOURCE_DIR}/avs3-renderer-hardening.patch
        COMMAND ${EXEC} git apply
        ${CMAKE_CURRENT_SOURCE_DIR}/avs3-renderer-hardening.patch
    CONFIGURE_COMMAND ${EXEC} CONF=1 cmake
        -S <SOURCE_DIR>/av3adecoder
        -B <BINARY_DIR>
        -G Ninja
        -DCMAKE_BUILD_TYPE=Release
        -DCMAKE_TOOLCHAIN_FILE=${TOOLCHAIN_FILE}
        -DCMAKE_INSTALL_PREFIX=${MINGW_INSTALL_PREFIX}
        -DCMAKE_FIND_ROOT_PATH=${MINGW_INSTALL_PREFIX}
        -DBUILD_SHARED_LIBS=OFF
        -DAVS3_BUILD_RENDERER=ON
        -DRENDERER_ROOT=<SOURCE_DIR>/av3a_binaural_render/AudioDecoder/av3a_binaural_render
    BUILD_COMMAND ${EXEC} ninja -C <BINARY_DIR>
    INSTALL_COMMAND ${EXEC} ninja -C <BINARY_DIR> install
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

force_rebuild_git(avs3-audiodec)
cleanup(avs3-audiodec install)
