package cn.jinban.quickentry;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.*;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ImageUploadTest {
    @TempDir Path data;
    QuickEntryController controller(){
        var service=mock(TaskService.class);when(service.require("task")).thenReturn(Map.of("id","task","status","ready"));
        when(service.dataRoot()).thenReturn(data);
        return new QuickEntryController(service,mock(StoreMapper.class));
    }
    @Test void clipboardPngIsPersistedAndCanBeReadThroughAssetEndpoint()throws Exception{
        var bytes=new ByteArrayOutputStream();javax.imageio.ImageIO.write(new BufferedImage(16,8,BufferedImage.TYPE_INT_RGB),"png",bytes);
        var controller=controller();
        var result=(Map<?,?>)controller.image("task",new MockMultipartFile("file","截图.png","image/png",bytes.toByteArray()));
        assertEquals(16,result.get("width_px"));assertEquals(8,result.get("height_px"));
        String url=result.get("url").toString(),key=java.net.URLDecoder.decode(url.substring(url.indexOf('=')+1),java.nio.charset.StandardCharsets.UTF_8);
        assertTrue(key.startsWith("tasks/task/manual-images/"));
        assertArrayEquals(bytes.toByteArray(),Files.readAllBytes(data.resolve(key)));
        var response=controller.asset(key);assertEquals(200,response.getStatusCode().value());assertNotNull(response.getBody());
    }
    @Test void renamedHtmlIsRejected(){
        var controller=controller();
        var exception=assertThrows(ResponseStatusException.class,()->controller.image("task",new MockMultipartFile("file","fake.png","image/png","<script>bad</script>".getBytes())));
        assertEquals(400,exception.getStatusCode().value());
    }
    @Test void emptyImageIsRejected(){
        var exception=assertThrows(ResponseStatusException.class,()->controller().image("task",new MockMultipartFile("file",new byte[0])));
        assertTrue(exception.getReason().contains("图片为空"));
    }
}
