FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY apps/api apps/api
RUN mkdir -p /root/.m2 && cat > /root/.m2/settings.xml <<'EOF'
<settings>
  <mirrors>
    <mirror>
      <id>aliyun</id>
      <mirrorOf>*</mirrorOf>
      <url>https://maven.aliyun.com/repository/public</url>
    </mirror>
  </mirrors>
</settings>
EOF
RUN mvn -f apps/api/pom.xml -q -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/apps/api/target/*.jar /app/app.jar
ENV API_PORT=2002
EXPOSE 2002
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
