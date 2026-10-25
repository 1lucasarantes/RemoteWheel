plugins {
  alias(libs.plugins.android.application)
}

android {
  namespace = "com.lucas.remotewheel"
  compileSdk = 35

  defaultConfig {
    applicationId = "com.lucas.remotewheel"
    minSdk = 28
    targetSdk = 35
    versionCode = 1
    versionName = "1.0"
  }

  buildTypes {
    release {
      isMinifyEnabled = false
      proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
  }

  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
  }

  buildFeatures {
    compose = false
    aidl = false
    buildConfig = false
    shaders = false
  }
}

kotlin {
  jvmToolchain(21)
}

dependencies {
  implementation(libs.androidx.core.ktx)
}
