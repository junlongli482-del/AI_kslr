package cn.jinban;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

/** Single-operator local prototype. Server binds loopback; no public deployment. */
@Configuration
public class LocalSecurity {
    @Bean SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http.csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .headers(headers -> headers.contentTypeOptions(c -> {}))
            .build();
    }
}
