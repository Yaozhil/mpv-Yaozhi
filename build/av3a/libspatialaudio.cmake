ExternalProject_Add(libspatialaudio
    GIT_REPOSITORY https://github.com/videolan/libspatialaudio.git
    GIT_TAG d149ed9744fd399b835c6f2920511f8cbcfce5ea
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    GIT_SUBMODULES ""
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ${EXEC} CONF=1 cmake
        -S <SOURCE_DIR>
        -B <BINARY_DIR>
        -G Ninja
        -DCMAKE_BUILD_TYPE=Release
        -DCMAKE_TOOLCHAIN_FILE=${TOOLCHAIN_FILE}
        -DCMAKE_INSTALL_PREFIX=${MINGW_INSTALL_PREFIX}
        -DCMAKE_INSTALL_LIBDIR=lib
        -DCMAKE_FIND_ROOT_PATH=${MINGW_INSTALL_PREFIX}
        -DBUILD_SHARED_LIBS=OFF
        -DHAVE_MIT_HRTF=ON
        -DBUILD_TESTING=OFF
        -DCMAKE_DISABLE_FIND_PACKAGE_MySofa:BOOL=TRUE
        -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
    BUILD_COMMAND python3 ${PROJECT_SOURCE_DIR}/speaker-lock-tools/verify-speakers-build.py
        --winbuild ${PROJECT_SOURCE_DIR}
        --config ${PROJECT_SOURCE_DIR}/speaker-lock-tools/config
        --source <SOURCE_DIR> --build <BINARY_DIR> --prefix ${MINGW_INSTALL_PREFIX}
        --phase before
        COMMAND ${EXEC} ninja -C <BINARY_DIR>
    INSTALL_COMMAND ${EXEC} ninja -C <BINARY_DIR> install
        COMMAND python3 ${PROJECT_SOURCE_DIR}/speaker-lock-tools/verify-speakers-build.py
        --winbuild ${PROJECT_SOURCE_DIR}
        --config ${PROJECT_SOURCE_DIR}/speaker-lock-tools/config
        --source <SOURCE_DIR> --build <BINARY_DIR> --prefix ${MINGW_INSTALL_PREFIX}
        --phase after
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

force_rebuild_git(libspatialaudio)
# Retain this new dependency's exact source and build directory for the
# appended speaker identity gate. The historical cleanup helper stays intact.
