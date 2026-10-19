package cn.jinban;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class QuickEntryApplication {
    public static void main(String[] args) { SpringApplication.run(QuickEntryApplication.class, args); }
}
